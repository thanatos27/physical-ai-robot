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


class HardwareExecutorReportMirrorTest(unittest.TestCase):
    """Milestone 6: Vision の console report を Display / LED へもミラーする (AC-18)。"""

    def test_person_detected_is_mirrored_to_display_and_green_led(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter, stream=io.StringIO())

        executor.execute(Action(ActionType.REPORT_PERSON_DETECTED, "Person detected"))

        self.assertEqual(
            adapter.calls, [("display", "Person detected"), ("set_led", "GREEN")]
        )

    def test_no_person_turns_led_off(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter, stream=io.StringIO())

        executor.execute(Action(ActionType.REPORT_NO_PERSON, "No person detected"))

        self.assertIn(("set_led", "OFF"), adapter.calls)

    def test_mirror_failure_does_not_fail_the_console_report(self):
        adapter = FakeHardwareAdapter(fail_on=frozenset({"display", "set_led"}))
        stream = io.StringIO()
        executor = HardwareExecutor(adapter, stream=stream)

        result = executor.execute(
            Action(ActionType.REPORT_PERSON_DETECTED, "Person detected")
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(stream.getvalue(), "Person detected\n")
        self.assertFalse(executor.device_status()["display"].available)

    def test_repeated_identical_report_does_not_redraw(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter, stream=io.StringIO())
        action = Action(ActionType.REPORT_PERSON_DETECTED, "Person detected")

        for _ in range(5):
            executor.execute(action)

        self.assertEqual(
            adapter.calls, [("display", "Person detected"), ("set_led", "GREEN")]
        )

    def test_changed_report_is_redrawn(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter, stream=io.StringIO())

        executor.execute(Action(ActionType.REPORT_PERSON_DETECTED, "Person detected"))
        executor.execute(Action(ActionType.REPORT_NO_PERSON, "No person detected"))
        executor.execute(Action(ActionType.REPORT_PERSON_DETECTED, "Person detected"))

        displays = [value for method, value in adapter.calls if method == "display"]
        self.assertEqual(
            displays, ["Person detected", "No person detected", "Person detected"]
        )

    def test_display_is_retried_after_a_failure(self):
        # 失敗した出力は「前回出力済み」として扱わず、次回同じ内容でも再試行する。
        adapter = FakeHardwareAdapter(fail_on=frozenset({"display"}))
        executor = HardwareExecutor(adapter, stream=io.StringIO())
        action = Action(ActionType.DISPLAY_MESSAGE, "hello")

        executor.execute(action)
        adapter.fail_on = frozenset()
        result = executor.execute(action)

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(adapter.calls, [("display", "hello")])

    def test_play_audio_is_not_deduplicated(self):
        adapter = FakeHardwareAdapter()
        executor = HardwareExecutor(adapter)
        action = Action(ActionType.PLAY_AUDIO, "chime.wav")

        executor.execute(action)
        executor.execute(action)

        self.assertEqual(
            adapter.calls, [("play_audio", "chime.wav"), ("play_audio", "chime.wav")]
        )


if __name__ == "__main__":
    unittest.main()
