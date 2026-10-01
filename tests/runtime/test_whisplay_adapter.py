"""RealWhisplayAdapter のラッパーロジックのテスト。

PiSugar の `whisplay_client` は実機 (Raspberry Pi + Whisplay HAT) 上にしか
存在しないため、sys.modules に偽モジュールを差し込んで検証する。実機での
動作確認は Real-device Verification として別途行う (AGENTS.md)。
"""

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


def fake_client(board=None, raises=None):
    module = types.ModuleType("whisplay_client")

    def create_whisplay_hardware(**kwargs):
        if raises is not None:
            raise raises
        return board

    module.create_whisplay_hardware = create_whisplay_hardware
    return mock.patch.dict(sys.modules, {"whisplay_client": module})


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
        ), mock.patch.dict(sys.modules):
            sys.modules.pop("whisplay_client", None)
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


if __name__ == "__main__":
    unittest.main()
