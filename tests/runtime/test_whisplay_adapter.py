"""RealWhisplayAdapter のラッパーロジックのテスト。

PiSugar の `whisplay_client` は実機 (Raspberry Pi + Whisplay HAT) 上にしか
存在しないため、sys.modules に偽モジュールを差し込んで検証する。実機での
動作確認は Real-device Verification として別途行う (AGENTS.md)。
"""

import contextlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from runtime.adapters import DeviceUnavailableError
from runtime.adapters.whisplay import BUTTON_PRESSED, RealWhisplayAdapter, led_rgb
from runtime.dispatch import DispatchQueue

try:
    import PIL  # noqa: F401

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class FakeBoard:
    LCD_WIDTH = 4
    LCD_HEIGHT = 2

    def __init__(self, fail=None):
        self.fail = fail or set()
        self.calls = []
        self.press_callback = None

    def _record(self, name, *args):
        if name in self.fail:
            raise OSError(f"{name} broken")
        self.calls.append((name, *args))

    def set_backlight(self, level):
        self._record("set_backlight", level)

    def set_rgb(self, r, g, b):
        self._record("set_rgb", r, g, b)

    def draw_image(self, x, y, width, height, data):
        self._record("draw_image", x, y, width, height, len(data))

    def on_button_press(self, callback):
        self.press_callback = callback

    def cleanup(self):
        self._record("cleanup")


@contextlib.contextmanager
def isolated_driver_import(module=None):
    """本物の PiSugar whisplay_client から隔離する。

    Raspberry Pi 上では ~/Whisplay/runtime に本物の whisplay_client.py があり、
    sys.path から見えると自動テストが実機の Whisplay を初期化してしまう
    (Milestone 10 で Pi 上の実行時に発生)。テストの間だけ、whisplay_client.py を
    含むディレクトリを sys.path から除き、読み込み済みのモジュールも外す。
    module を渡した場合は、それを whisplay_client として使わせる。
    """
    path = [
        p for p in sys.path
        if not os.path.isfile(os.path.join(p or os.getcwd(), "whisplay_client.py"))
    ]
    with mock.patch.object(sys, "path", path), mock.patch.dict(sys.modules):
        sys.modules.pop("whisplay_client", None)
        if module is not None:
            sys.modules["whisplay_client"] = module
        yield


def fake_client(board=None, raises=None):
    module = types.ModuleType("whisplay_client")

    def create_whisplay_hardware(**kwargs):
        if raises is not None:
            raise raises
        return board

    module.create_whisplay_hardware = create_whisplay_hardware
    return isolated_driver_import(module)


class RealWhisplayAdapterTest(unittest.TestCase):
    def test_button_press_pushes_button_pressed_event(self):
        board = FakeBoard()
        dispatch = DispatchQueue()
        with fake_client(board):
            RealWhisplayAdapter(dispatch)

        board.press_callback()

        self.assertEqual(dispatch.pop().type, BUTTON_PRESSED)

    def test_set_led_maps_named_state_to_rgb(self):
        board = FakeBoard()
        with fake_client(board):
            adapter = RealWhisplayAdapter(DispatchQueue())

        adapter.set_led("green")

        self.assertIn(("set_rgb", 0, 255, 0), board.calls)

    def test_unknown_led_state_is_device_unavailable(self):
        with self.assertRaises(DeviceUnavailableError):
            led_rgb("PURPLE")

    def test_board_error_becomes_device_unavailable(self):
        board = FakeBoard(fail={"set_rgb"})
        with fake_client(board):
            adapter = RealWhisplayAdapter(DispatchQueue())

        with self.assertRaises(DeviceUnavailableError):
            adapter.set_led("RED")

    def test_cleanup_turns_led_off_and_releases_board(self):
        board = FakeBoard()
        with fake_client(board):
            adapter = RealWhisplayAdapter(DispatchQueue())

        adapter.cleanup()

        self.assertEqual(board.calls[-2:], [("set_rgb", 0, 0, 0), ("cleanup",)])

    def test_cleanup_never_raises(self):
        board = FakeBoard(fail={"set_rgb", "cleanup"})
        with fake_client(board):
            adapter = RealWhisplayAdapter(DispatchQueue())

        adapter.cleanup()  # 例外を出さない

    def test_board_acquisition_failure_is_device_unavailable(self):
        with fake_client(raises=OSError("GPIO busy")):
            with self.assertRaises(DeviceUnavailableError):
                RealWhisplayAdapter(DispatchQueue())

    def test_missing_driver_is_device_unavailable(self):
        with tempfile.TemporaryDirectory() as empty_dir, mock.patch.dict(
            "os.environ", {"WHISPLAY_DRIVER_DIR": empty_dir}
        ), isolated_driver_import():
            with self.assertRaises(DeviceUnavailableError):
                RealWhisplayAdapter(DispatchQueue())

    @unittest.skipUnless(HAS_PIL, "Pillow is not installed")
    def test_display_draws_full_screen_rgb565_frame(self):
        board = FakeBoard()
        with fake_client(board):
            adapter = RealWhisplayAdapter(DispatchQueue())

        adapter.display("hi")

        # 4x2 ピクセル x 2 bytes (RGB565)
        self.assertIn(("draw_image", 0, 0, 4, 2, 16), board.calls)


class RecordingSpi:
    def __init__(self, board):
        self._board = board
        self._hz = 100_000_000

    @property
    def max_speed_hz(self):
        return self._hz

    @max_speed_hz.setter
    def max_speed_hz(self, hz):
        self._board.calls.append(("spi_speed", hz))
        self._hz = hz


class FakeDirectBoard(FakeBoard):
    """PiSugar WhisplayBoard (直接制御) を模擬: spi と LCD 初期化メソッドを持つ。"""

    def __init__(self, fail=None):
        super().__init__(fail)
        self.spi = RecordingSpi(self)

    def _reset_lcd(self):
        self._record("reset_lcd")

    def _init_display(self):
        self._record("init_display")

    def fill_screen(self, color):
        self._record("fill_screen", color)


class WhisplaySpiSpeedTest(unittest.TestCase):
    """Design Issue #8: LCD の SPI クロックを暫定 8 MHz にし、その速度で再初期化する。"""

    def _open(self, board, env=None):
        environ = {k: v for k, v in (env or {}).items()}
        with fake_client(board), mock.patch.dict("os.environ", environ):
            if "WHISPLAY_SPI_HZ" not in environ:
                import os

                os.environ.pop("WHISPLAY_SPI_HZ", None)
            return RealWhisplayAdapter(DispatchQueue())

    def test_default_is_8mhz_and_lcd_is_reinitialized_before_backlight(self):
        board = FakeDirectBoard()

        self._open(board)

        self.assertEqual(board.spi.max_speed_hz, 8_000_000)
        self.assertEqual(
            board.calls[:5],
            [
                ("spi_speed", 8_000_000),
                ("reset_lcd",),
                ("init_display",),
                ("fill_screen", 0),
                ("set_backlight", 70),
            ],
        )

    def test_env_overrides_speed_for_milestone_11_comparison(self):
        board = FakeDirectBoard()

        self._open(board, {"WHISPLAY_SPI_HZ": "16000000"})

        self.assertEqual(board.spi.max_speed_hz, 16_000_000)

    def test_invalid_env_falls_back_to_default(self):
        board = FakeDirectBoard()

        with self.assertLogs("runtime.adapters.whisplay", level="WARNING") as logs:
            self._open(board, {"WHISPLAY_SPI_HZ": "fast"})

        self.assertEqual(board.spi.max_speed_hz, 8_000_000)
        self.assertIn("Invalid WHISPLAY_SPI_HZ", "\n".join(logs.output))

    def test_daemon_mode_without_spi_warns_and_continues(self):
        board = FakeBoard()  # spi を持たない (WhisplayDaemonProxy 相当)

        with self.assertLogs("runtime.adapters.whisplay", level="WARNING") as logs:
            adapter = self._open(board)

        self.assertIn("not accessible", "\n".join(logs.output))
        adapter.set_led("RED")
        self.assertIn(("set_rgb", 255, 0, 0), board.calls)

    def test_reinit_failure_is_not_fatal(self):
        board = FakeDirectBoard(fail={"init_display"})

        with self.assertLogs("runtime.adapters.whisplay", level="WARNING") as logs:
            self._open(board)

        self.assertIn("re-initialization failed", "\n".join(logs.output))
        self.assertIn(("set_backlight", 70), board.calls)


if __name__ == "__main__":
    unittest.main()
