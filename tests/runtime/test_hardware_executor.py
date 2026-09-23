import io
import unittest

from runtime.action import HardwareExecutor
from runtime.adapters.mock import FakeHardwareAdapter
from runtime.models import Action, ActionStatus, ActionType


class HardwareExecutorTest(unittest.TestCase):
    def test_display_message_calls_adapter(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter)

        result = executor.execute(Action(ActionType.DISPLAY_MESSAGE, "hello"))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(adapter.calls, [("display", "hello")])

    def test_set_led_calls_adapter(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter)

        result = executor.execute(Action(ActionType.SET_LED, "RED"))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(adapter.calls, [("set_led", "RED")])

    def test_play_audio_calls_adapter(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter)

        result = executor.execute(Action(ActionType.PLAY_AUDIO, "chime.wav"))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(adapter.calls, [("play_audio", "chime.wav")])

    def test_report_actions_still_print_to_console(self):
        stream = io.StringIO()
        executor = HardwareExecutor(FakeHardwareAdapter(), stream=stream)

        result = executor.execute(
            Action(ActionType.REPORT_PERSON_DETECTED, "Person detected")
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(stream.getvalue(), "Person detected\n")

    def test_unsupported_action_returns_failed(self):
        executor = HardwareExecutor(FakeHardwareAdapter())

        result = executor.execute(Action("DANCE", "x"))

        self.assertEqual(result.status, ActionStatus.FAILED)

    def test_device_unavailable_returns_failed_without_raising(self):
        adapter = FakeHardwareAdapter(fail_on=frozenset({"display"}))
        executor = HardwareExecutor(adapter)

        result = executor.execute(Action(ActionType.DISPLAY_MESSAGE, "hello"))

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertIn("display", result.detail)

    def test_device_status_reflects_last_outcome(self):
        adapter = FakeHardwareAdapter(fail_on=frozenset({"display"}))
        executor = HardwareExecutor(adapter)

        executor.execute(Action(ActionType.DISPLAY_MESSAGE, "hello"))
        status = executor.device_status()

        self.assertFalse(status["display"].available)
        self.assertIn("display", status["display"].detail)

    def test_device_status_updates_to_available_after_success(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter)

        executor.execute(Action(ActionType.SET_LED, "RED"))
        status = executor.device_status()

        self.assertTrue(status["set_led"].available)

    def test_one_device_failure_does_not_block_other_actions(self):
        # 非必須 I/O の1つが失敗しても Runtime 全体を止めない (NFR-04, AC-24)。
        adapter = FakeHardwareAdapter(fail_on=frozenset({"display"}))
        executor = HardwareExecutor(adapter)

        failed = executor.execute(Action(ActionType.DISPLAY_MESSAGE, "hello"))
        ok = executor.execute(Action(ActionType.SET_LED, "RED"))

        self.assertEqual(failed.status, ActionStatus.FAILED)
        self.assertEqual(ok.status, ActionStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
