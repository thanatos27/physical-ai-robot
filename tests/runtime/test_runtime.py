import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime.action import ActionPlanner, ConsoleExecutor
from runtime.input import JsonlInputSource, parse_detection_event
from runtime.models import Action, ActionResult, ActionStatus, ActionType
from runtime.observation import ObservationAdapter
from runtime.reasoner import RuleBasedReasoner
from runtime.robot_logger import JsonlRobotDataLogger
from runtime.robot_runtime import RobotRuntime, RuntimeState, main

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "detections_sample.jsonl"

EXPECTED_KEYS = {
    "schema_version",
    "loop_id",
    "timestamp",
    "observation",
    "decision",
    "action",
    "result",
}
EXPECTED_CONSOLE = [
    "Person detected",
    "No person detected",
    "No person detected",
    "Person detected",
]


class RecordingLogger:
    def __init__(self, fail_on_log=None):
        self.records = []
        self.closed = False
        self._fail_on_log = fail_on_log

    def log(self, record):
        if self._fail_on_log is not None:
            raise self._fail_on_log
        self.records.append(record)

    def close(self):
        self.closed = True


class CallbackExecutor:
    def __init__(self, result, on_execute=None):
        self._result = result
        self._on_execute = on_execute

    def execute(self, action):
        if self._on_execute is not None:
            self._on_execute()
        return self._result


def build_runtime(source, data_logger, executor=None, reasoner=None):
    return RobotRuntime(
        input_source=source,
        adapter=ObservationAdapter(),
        reasoner=reasoner or RuleBasedReasoner(),
        planner=ActionPlanner(),
        executor=executor or ConsoleExecutor(io.StringIO()),
        data_logger=data_logger,
    )


def read_records(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def two_events():
    line = '{"timestamp":%d,"detections":[]}'
    return [parse_detection_event(line % 1), parse_detection_event(line % 2)]


class RobotRuntimeTest(unittest.TestCase):
    def test_fixture_replay_writes_one_record_per_valid_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "robot.jsonl"
            stdout = io.StringIO()
            with FIXTURE.open(encoding="utf-8") as stream:
                runtime = build_runtime(
                    JsonlInputSource(stream),
                    JsonlRobotDataLogger(log_path),
                    executor=ConsoleExecutor(stdout),
                )
                with self.assertLogs("runtime.input", level="WARNING") as warnings:
                    count = runtime.run()

            records = read_records(log_path)

        self.assertEqual(count, 4)
        self.assertEqual(len(warnings.records), 3)
        self.assertEqual(stdout.getvalue().splitlines(), EXPECTED_CONSOLE)
        self.assertEqual(len(records), 4)
        for record in records:
            self.assertEqual(set(record), EXPECTED_KEYS)
            self.assertEqual(record["schema_version"], "0.1")
            self.assertEqual(record["result"], {"status": "SUCCESS", "detail": None})
            self.assertEqual(record["timestamp"], record["observation"]["timestamp"])
        self.assertEqual([r["loop_id"] for r in records], [1, 2, 3, 4])
        self.assertEqual(
            [r["decision"]["type"] for r in records],
            ["PERSON_DETECTED", "NO_PERSON", "NO_PERSON", "PERSON_DETECTED"],
        )
        self.assertEqual(records[0]["action"]["type"], "REPORT_PERSON_DETECTED")
        self.assertEqual(records[0]["timestamp"], 1789762879207)
        first_object = records[0]["observation"]["objects"][0]
        self.assertEqual(first_object["type"], "person")
        self.assertEqual(
            first_object["bounding_box"],
            {"x": 3, "y": 2, "width": 1242, "height": 1044},
        )

    def test_zero_detections_is_logged_as_an_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "robot.jsonl"
            with FIXTURE.open(encoding="utf-8") as stream:
                runtime = build_runtime(
                    JsonlInputSource(stream), JsonlRobotDataLogger(log_path)
                )
                with self.assertLogs("runtime.input", level="WARNING"):
                    runtime.run()
            records = read_records(log_path)

        self.assertEqual(records[2]["observation"]["objects"], [])
        self.assertEqual(records[2]["decision"], {"type": "NO_PERSON"})

    def test_failed_action_result_is_logged_and_loop_continues(self):
        data_logger = RecordingLogger()
        failed = ActionResult(ActionStatus.FAILED, "device busy")
        runtime = build_runtime(
            two_events(), data_logger, executor=CallbackExecutor(failed)
        )

        count = runtime.run()

        self.assertEqual(count, 2)
        self.assertEqual([r.result for r in data_logger.records], [failed, failed])

    def test_console_executor_returns_failed_for_unsupported_action(self):
        executor = ConsoleExecutor(io.StringIO())

        result = executor.execute(Action(type="DANCE", message="x"))

        self.assertEqual(result.status, ActionStatus.FAILED)

    def test_console_executor_writes_message(self):
        stream = io.StringIO()

        result = ConsoleExecutor(stream).execute(
            Action(ActionType.REPORT_PERSON_DETECTED, "Person detected")
        )

        self.assertEqual(result, ActionResult(ActionStatus.SUCCESS))
        self.assertEqual(stream.getvalue(), "Person detected\n")

    def test_unexpected_reasoner_error_propagates_and_closes_logger(self):
        data_logger = RecordingLogger()
        reasoner = mock.Mock()
        reasoner.reason.side_effect = RuntimeError("boom")
        runtime = build_runtime(two_events(), data_logger, reasoner=reasoner)

        with self.assertRaisesRegex(RuntimeError, "boom"):
            runtime.run()

        self.assertTrue(data_logger.closed)
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    def test_data_logger_failure_propagates_and_closes_logger(self):
        data_logger = RecordingLogger(fail_on_log=OSError("disk full"))
        runtime = build_runtime(two_events(), data_logger)

        with self.assertRaisesRegex(OSError, "disk full"):
            runtime.run()

        self.assertTrue(data_logger.closed)

    def test_eof_stops_runtime_and_closes_logger(self):
        data_logger = RecordingLogger()
        runtime = build_runtime(two_events(), data_logger)

        runtime.run()

        self.assertTrue(data_logger.closed)
        self.assertEqual(runtime.state, RuntimeState.STOPPED)

    def test_stop_request_finishes_current_event_then_stops(self):
        data_logger = RecordingLogger()
        holder = {}
        executor = CallbackExecutor(
            ActionResult(ActionStatus.SUCCESS),
            on_execute=lambda: holder["runtime"].request_stop(),
        )
        runtime = build_runtime(two_events(), data_logger, executor=executor)
        holder["runtime"] = runtime

        count = runtime.run()

        self.assertEqual(count, 1)
        self.assertEqual(len(data_logger.records), 1)
        self.assertTrue(data_logger.closed)

    def test_keyboard_interrupt_while_waiting_for_input_stops_normally(self):
        data_logger = RecordingLogger()

        def source():
            yield two_events()[0]
            raise KeyboardInterrupt

        runtime = build_runtime(source(), data_logger)

        count = runtime.run()

        self.assertEqual(count, 1)
        self.assertTrue(data_logger.closed)
        self.assertEqual(runtime.state, RuntimeState.STOPPED)


class MainTest(unittest.TestCase):
    def test_main_processes_stdin_and_returns_zero(self):
        # main() は Phase 0.8 Dispatch path (DispatchingVisionSource) を使う。
        # State Coalescing により raw DetectionEvent 数と RobotLoopRecord 数の
        # 一致は要求しない (docs/specs/phase-0.8-implementation-plan.md
        # #Regression Boundary)。「1件以上処理される」「最終的に最新の Vision
        # State へ追従する」ことだけを確認する。
        stdin = io.StringIO(FIXTURE.read_text(encoding="utf-8"))
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "nested" / "robot.jsonl"
            with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout):
                exit_code = main(["--log-path", str(log_path), "--log-level", "ERROR"])
            records = read_records(log_path)

        self.assertEqual(exit_code, 0)
        console_lines = stdout.getvalue().splitlines()
        self.assertGreaterEqual(len(console_lines), 1)
        self.assertEqual(console_lines[-1], EXPECTED_CONSOLE[-1])
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[-1]["decision"]["type"], "PERSON_DETECTED")
        for record in records:
            self.assertEqual(set(record), EXPECTED_KEYS)
            self.assertEqual(record["schema_version"], "0.1")

    def test_main_returns_one_on_unexpected_runtime_error(self):
        stdin = io.StringIO(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "robot.jsonl"
            with mock.patch("sys.stdin", stdin), mock.patch.object(
                RuleBasedReasoner, "reason", side_effect=RuntimeError("boom")
            ):
                with self.assertLogs("runtime.robot_runtime", level="ERROR") as logs:
                    exit_code = main(["--log-path", str(log_path)])

        self.assertEqual(exit_code, 1)
        self.assertIn("boom", "\n".join(logs.output))


class CliEndToEndTest(unittest.TestCase):
    def test_module_runs_with_stdin_redirect(self):
        # Dispatch path (State Coalescing) のため件数一致は要求しない。
        # MainTest.test_main_processes_stdin_and_returns_zero と同じ基準。
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "robot.jsonl"
            with FIXTURE.open("rb") as stdin:
                proc = subprocess.run(
                    [sys.executable, "-m", "runtime.robot_runtime", "--log-path", str(log_path)],
                    stdin=stdin,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    cwd=REPO_ROOT,
                    timeout=30,
                )
            records = read_records(log_path)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        console_lines = proc.stdout.splitlines()
        self.assertGreaterEqual(len(console_lines), 1)
        self.assertEqual(console_lines[-1], EXPECTED_CONSOLE[-1])
        self.assertIn("WARNING", proc.stderr)
        self.assertIn("Robot Runtime started", proc.stderr)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[-1]["decision"]["type"], "PERSON_DETECTED")


if __name__ == "__main__":
    unittest.main()
