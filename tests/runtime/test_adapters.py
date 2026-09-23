import unittest

from runtime.adapters import DeviceUnavailableError
from runtime.adapters.mock import BUTTON_PRESSED, FakeButtonSource, FakeHardwareAdapter
from runtime.dispatch import DispatchQueue


class FakeHardwareAdapterTest(unittest.TestCase):
    def test_records_calls(self):
        adapter = FakeHardwareAdapter()

        adapter.display("hello")
        adapter.set_led("RED")
        adapter.play_audio("chime.wav")

        self.assertEqual(
            adapter.calls,
            [("display", "hello"), ("set_led", "RED"), ("play_audio", "chime.wav")],
        )

    def test_fail_on_raises_device_unavailable_error(self):
        adapter = FakeHardwareAdapter(fail_on=frozenset({"display"}))

        with self.assertRaises(DeviceUnavailableError):
            adapter.display("hello")

        # 失敗したメソッドは記録されない。
        self.assertEqual(adapter.calls, [])

        # 失敗していないメソッドは通常通り動く (非必須 I/O 障害の分離)。
        adapter.set_led("RED")
        self.assertEqual(adapter.calls, [("set_led", "RED")])


class FakeButtonSourceTest(unittest.TestCase):
    def test_press_pushes_button_pressed_event(self):
        dispatch = DispatchQueue()
        button = FakeButtonSource(dispatch)

        button.press()

        event = dispatch.pop()
        self.assertEqual(event.type, BUTTON_PRESSED)


if __name__ == "__main__":
    unittest.main()
