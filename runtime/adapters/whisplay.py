"""Real Whisplay Adapter (Milestone 6)。

実機 API は Milestone 5 で PiSugar/Whisplay (https://github.com/PiSugar/Whisplay)
の `runtime/whisplay_client.py` / `example/test.py` を実機上で読み、実際の
board オブジェクトのメソッドに合わせて実装した
(docs/progress/phase-0.8-progress.md #4.6)。

PiSugar の driver コードはこのリポジトリへ vendor せず、Phase 0.5 の
Hailo / rpicam-apps と同様に外部システム依存として扱う。クローン場所は
環境変数 WHISPLAY_DRIVER_DIR (既定: ~/Whisplay/runtime) で指定する。

`create_whisplay_hardware()` は whisplay-daemon が動いていれば daemon 経由、
無ければ WhisplayBoard (直接制御) を返す。どちらを使うかの判断は PiSugar 側の
ロジックに委ねる。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Callable

from ..dispatch import DispatchQueue
from ..event import RuntimeEvent
from . import DeviceUnavailableError

logger = logging.getLogger(__name__)

BUTTON_PRESSED = "BUTTON_PRESSED"
AUDIO_DEVICE = "whisplaysound"

_DEFAULT_WHISPLAY_RUNTIME_DIR = os.path.expanduser("~/Whisplay/runtime")

# AI HAT+ 2 上に積層すると、PiSugar 既定の 100 MHz では LCD 表示が不安定になる
# ことがあるため、暫定で 8 MHz とする (Design Issue #8)。Milestone 11 で
# 8 / 16 / 32 MHz を比較して最終値を決めるまで、WHISPLAY_SPI_HZ で上書きできる。
DEFAULT_SPI_SPEED_HZ = 8_000_000
_BACKGROUND = (10, 14, 22)
_FOREGROUND = (255, 255, 255)

LED_COLORS: dict[str, tuple[int, int, int]] = {
    "OFF": (0, 0, 0),
    "RED": (255, 0, 0),
    "GREEN": (0, 255, 0),
    "BLUE": (0, 0, 255),
    "WHITE": (255, 255, 255),
    "YELLOW": (255, 255, 0),
}


def whisplay_runtime_dir() -> str:
    return os.environ.get("WHISPLAY_DRIVER_DIR", _DEFAULT_WHISPLAY_RUNTIME_DIR)


def spi_speed_hz() -> int:
    raw = os.environ.get("WHISPLAY_SPI_HZ")
    if raw is None:
        return DEFAULT_SPI_SPEED_HZ
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning(
            "Invalid WHISPLAY_SPI_HZ=%r; using %d", raw, DEFAULT_SPI_SPEED_HZ
        )
        return DEFAULT_SPI_SPEED_HZ
    return value


def _import_create_whisplay_hardware() -> Callable[..., object]:
    runtime_dir = whisplay_runtime_dir()
    if runtime_dir not in sys.path:
        sys.path.append(runtime_dir)
    try:
        from whisplay_client import create_whisplay_hardware  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DeviceUnavailableError(
            f"whisplay_client is not importable from {runtime_dir} "
            f"(set WHISPLAY_DRIVER_DIR if the Whisplay clone is elsewhere): {exc}"
        ) from exc
    return create_whisplay_hardware


def rgb565_bytes(image) -> bytes:
    """PIL Image を Whisplay LCD (ST7789) 用の RGB565 big-endian バイト列へ変換する。"""
    rgb = image.convert("RGB")
    output = bytearray()
    for r, g, b in rgb.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        output.append((value >> 8) & 0xFF)
        output.append(value & 0xFF)
    return bytes(output)


def led_rgb(state: str) -> tuple[int, int, int]:
    rgb = LED_COLORS.get(state.upper())
    if rgb is None:
        raise DeviceUnavailableError(f"unknown LED state: {state!r}")
    return rgb


class RealWhisplayAdapter:
    """HardwareAdapter Protocol の実機実装。

    Button press は Dispatch Queue へ `BUTTON_PRESSED` Event として投入する。
    Button release に対応する Event / Reason は Phase 0.8 時点では未定義の
    ため、release は Event を出さない。
    """

    def __init__(self, dispatch: DispatchQueue, backlight: int = 70) -> None:
        create_whisplay_hardware = _import_create_whisplay_hardware()
        try:
            self._board = create_whisplay_hardware(
                app_id="physical-ai-robot",
                display_name="Physical AI Robot",
                icon="R",
            )
        except Exception as exc:  # noqa: BLE001 - 起動時の取得失敗は縮退運転へ回す
            raise DeviceUnavailableError(f"failed to acquire Whisplay board: {exc}") from exc

        self._dispatch = dispatch
        self._configure_spi(spi_speed_hz())
        try:
            self._board.set_backlight(backlight)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Whisplay set_backlight failed: %s", exc)

        self._board.on_button_press(self._on_button_press)

    def _configure_spi(self, hz: int) -> None:
        """LCD の SPI クロックを設定し、その速度で LCD を初期化し直す (Design Issue #8)。

        PiSugar の WhisplayBoard は生成時に既定 (100 MHz) で LCD を初期化するため、
        積層時はその初期化自体が化けている可能性がある。速度を下げた後に
        初期化し直す。初期化には PiSugar の非公開メソッドを使う (実機で 8 MHz の
        安定を確認した診断と同じ呼び出し)。
        """
        spi = getattr(self._board, "spi", None)
        if spi is None:
            # whisplay-daemon 経由 (WhisplayDaemonProxy) では SPI を daemon が持つ。
            logger.warning("Whisplay SPI is not accessible (daemon mode?); speed not set")
            return
        try:
            spi.max_speed_hz = hz
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to set Whisplay SPI speed to %d Hz: %s", hz, exc)
            return

        reset = getattr(self._board, "_reset_lcd", None)
        init = getattr(self._board, "_init_display", None)
        if reset is None or init is None:
            logger.warning(
                "Whisplay LCD re-initialization is unavailable; "
                "LCD was initialized at the driver default speed"
            )
            return
        try:
            reset()
            init()
            self._board.fill_screen(0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Whisplay LCD re-initialization failed: %s", exc)
            return
        logger.info("Whisplay LCD SPI speed: %d Hz", hz)

    def _on_button_press(self) -> None:
        self._dispatch.push_event(RuntimeEvent(BUTTON_PRESSED))

    def display(self, message: str) -> None:
        try:
            from PIL import Image, ImageDraw

            width, height = self._board.LCD_WIDTH, self._board.LCD_HEIGHT
            image = Image.new("RGB", (width, height), _BACKGROUND)
            ImageDraw.Draw(image).text((16, 16), message, fill=_FOREGROUND)
            self._board.draw_image(0, 0, width, height, rgb565_bytes(image))
        except Exception as exc:  # noqa: BLE001
            raise DeviceUnavailableError(f"display failed: {exc}") from exc

    def set_led(self, state: str) -> None:
        r, g, b = led_rgb(state)
        try:
            self._board.set_rgb(r, g, b)
        except Exception as exc:  # noqa: BLE001
            raise DeviceUnavailableError(f"set_led failed: {exc}") from exc

    def play_audio(self, clip: str) -> None:
        # board に音声再生 API は無いため、Milestone 5 で確認した ALSA デバイスへ
        # aplay で直接再生する (PiSugar example/test.py と同じ方式)。
        try:
            subprocess.run(
                ["aplay", "-D", AUDIO_DEVICE, clip],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            raise DeviceUnavailableError(f"play_audio failed: {exc}") from exc

    def cleanup(self) -> None:
        try:
            self._board.set_rgb(0, 0, 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Whisplay LED off failed during cleanup: %s", exc)
        try:
            self._board.cleanup()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Whisplay cleanup failed: %s", exc)
