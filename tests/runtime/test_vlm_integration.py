"""Milestone 7 AC-EXT-04: Button → VLM Job → AI Result Event → Robot Event Log。

実 Hailo / カメラは使わず、FakeAIBackend で Runtime 側の配線を検証する。
実 worker (edge/vlm_worker) の動作は Real-device Verification で確認する。
"""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.action import ActionPlanner, AIRequestExecutor, HardwareExecutor
from runtime.adapters.mock import FakeHardwareAdapter
from runtime.ai import AIJobManager, AIJobStatus, AIJobType, FakeAIBackend
from runtime.dispatch import DispatchQueue
from runtime.event import RuntimeEvent
from runtime.models import Action, ActionStatus, ActionType, DecisionType
from runtime.observation import ObservationAdapter
from runtime.reasoner import RuleBasedReasoner
from runtime.robot_logger import JsonlRobotDataLogger
from runtime.robot_runtime import RobotRuntime, main

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "detections_sample.jsonl"


class RecordingManager:
    def __init__(self):
        self.jobs = []
        self.shutdown_called = False

    def submit(self, job):
        self.jobs.append(job)

    def shutdown(self):
        self.shutdown_called = True


class ActionPlannerVlmTest(unittest.TestCase):
    def test_vlm_requested_plans_request_vlm_with_feedback_message(self):
        from runtime.models import Decision

        action = ActionPlanner().plan(Decision(DecisionType.VLM_REQUESTED))

        self.assertEqual(action, Action(ActionType.REQUEST_VLM, "Button pressed"))


class AIRequestExecutorTest(unittest.TestCase):
    def _executor(self, adapter=None):
        adapter = adapter or FakeHardwareAdapter()
        manager = RecordingManager()
        executor = AIRequestExecutor(
            HardwareExecutor(adapter), manager, job_timeout=60.0, backend_name="test"
        )
        return executor, manager, adapter

    def test_request_vlm_submits_vlm_job_and_shows_feedback(self):
        executor, manager, adapter = self._executor()

        result = executor.execute(Action(ActionType.REQUEST_VLM, "Button pressed"))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(len(manager.jobs), 1)
        job = manager.jobs[0]
        self.assertEqual(job.type, AIJobType.VLM)
        self.assertEqual(job.timeout, 60.0)
        self.assertEqual(job.backend, "test")
        self.assertEqual(result.detail, f"job_id={job.job_id}")
        self.assertEqual(adapter.calls, [("display", "Button pressed")])

    def test_feedback_failure_does_not_fail_the_request(self):
        adapter = FakeHardwareAdapter(fail_on=frozenset({"display"}))
        executor, manager, _ = self._executor(adapter)

        result = executor.execute(Action(ActionType.REQUEST_VLM, "Button pressed"))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(len(manager.jobs), 1)

    def test_other_actions_are_delegated(self):
        executor, manager, adapter = self._executor()

        result = executor.execute(Action(ActionType.DISPLAY_MESSAGE, "hello"))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(manager.jobs, [])
        self.assertEqual(adapter.calls, [("display", "hello")])


def _dispatched(dispatch, count):
    for _ in range(count):
        yield dispatch.pop()


class ButtonToVlmEndToEndTest(unittest.TestCase):
    def test_button_request_and_ai_result_are_logged_and_correlated(self):
        dispatch = DispatchQueue()
        output = {"description": "a smartphone on a table", "load_s": 9.9}
        manager = AIJobManager(FakeAIBackend(default_output=output), dispatch.push_event)
        executor = AIRequestExecutor(
            HardwareExecutor(FakeHardwareAdapter()), manager, 60.0, "fake"
        )

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "robot.jsonl"
            runtime = RobotRuntime(
                input_source=_dispatched(dispatch, count=2),
                adapter=ObservationAdapter(),
                reasoner=RuleBasedReasoner(vlm_enabled=True),
                planner=ActionPlanner(),
                executor=executor,
                data_logger=JsonlRobotDataLogger(log_path),
            )
            dispatch.push_event(RuntimeEvent("BUTTON_PRESSED"))
            runtime.run()
            records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        request, result = records
        self.assertEqual(request["event"]["type"], "BUTTON_PRESSED")
        self.assertEqual(request["decision"]["type"], "VLM_REQUESTED")
        self.assertEqual(request["action"]["type"], "REQUEST_VLM")
        job_id = request["result"]["detail"].removeprefix("job_id=")

        # AC-EXT-04: AI Result Event の payload が Robot Event Log に記録される。
        self.assertEqual(result["event"]["type"], "AI_RESULT")
        payload = result["event"]["payload"]
        self.assertEqual(payload["job_id"], job_id)
        self.assertEqual(payload["type"], "VLM")
        self.assertEqual(payload["status"], AIJobStatus.COMPLETED.value)
        self.assertEqual(payload["output"], output)
        self.assertEqual(result["decision"]["type"], "AI_RESULT_RECEIVED")


class MainVlmTest(unittest.TestCase):
    def _run_main(self, extra_args):
        stdin = io.StringIO(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "robot.jsonl"
            with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", io.StringIO()):
                return main(["--log-path", str(log_path), "--hardware", "none", *extra_args])

    def test_vlm_falls_back_when_prerequisites_are_missing(self):
        with tempfile.TemporaryDirectory() as empty, mock.patch.dict(
            "os.environ",
            {"HAILO_GENAI_PYTHON": str(Path(empty) / "python"), "VLM_HEF_PATH": str(Path(empty) / "x.hef")},
        ):
            with self.assertLogs("runtime.robot_runtime", level="WARNING") as logs:
                exit_code = self._run_main(["--ai", "vlm"])

        self.assertEqual(exit_code, 0)
        self.assertIn("VLM unavailable", "\n".join(logs.output))

    def test_vlm_manager_is_shut_down_when_runtime_stops(self):
        manager = RecordingManager()
        with mock.patch("runtime.robot_runtime._open_vlm", return_value=manager):
            exit_code = self._run_main(["--ai", "vlm", "--log-level", "ERROR"])

        self.assertEqual(exit_code, 0)
        self.assertTrue(manager.shutdown_called)

    def test_ai_none_never_opens_vlm(self):
        with mock.patch("runtime.robot_runtime._open_vlm") as opener:
            exit_code = self._run_main(["--log-level", "ERROR"])

        self.assertEqual(exit_code, 0)
        opener.assert_not_called()

    def test_npu_mode_defaults_to_vision(self):
        from runtime.ai import NpuMode

        with mock.patch("runtime.robot_runtime._open_vlm", return_value=None) as opener:
            self._run_main(["--ai", "vlm", "--log-level", "ERROR"])

        arbiter = opener.call_args.args[1]
        self.assertIs(arbiter.mode, NpuMode.VISION)

    def test_npu_mode_ai_is_passed_to_the_vlm_manager(self):
        from runtime.ai import NpuMode

        with mock.patch("runtime.robot_runtime._open_vlm", return_value=None) as opener:
            self._run_main(["--ai", "vlm", "--npu-mode", "ai", "--log-level", "ERROR"])

        arbiter = opener.call_args.args[1]
        self.assertIs(arbiter.mode, NpuMode.AI)


class VisionModeButtonEndToEndTest(unittest.TestCase):
    """Issue #9: Vision 運用中 (--npu-mode vision) の VLM 要求は worker を起動せず
    理由付きで拒否され、Robot Event Log から追跡できる。"""

    def test_button_in_vision_mode_records_rejected_ai_result(self):
        from runtime.ai import NpuArbiter, NpuMode

        dispatch = DispatchQueue()
        backend = FakeAIBackend()
        with mock.patch.object(backend, "run", wraps=backend.run) as run:
            manager = AIJobManager(backend, dispatch.push_event, NpuArbiter(NpuMode.VISION))
            executor = AIRequestExecutor(HardwareExecutor(FakeHardwareAdapter()), manager, 60.0, "fake")

            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "robot.jsonl"
                runtime = RobotRuntime(
                    input_source=_dispatched(dispatch, count=2),
                    adapter=ObservationAdapter(),
                    reasoner=RuleBasedReasoner(vlm_enabled=True),
                    planner=ActionPlanner(),
                    executor=executor,
                    data_logger=JsonlRobotDataLogger(log_path),
                )
                dispatch.push_event(RuntimeEvent("BUTTON_PRESSED"))
                runtime.run()
                records = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines()]

        run.assert_not_called()
        request, result = records
        job_id = request["result"]["detail"].removeprefix("job_id=")
        payload = result["event"]["payload"]
        self.assertEqual(payload["job_id"], job_id)
        self.assertEqual(payload["status"], AIJobStatus.REJECTED.value)
        self.assertIn("VISION", payload["detail"])


if __name__ == "__main__":
    unittest.main()
