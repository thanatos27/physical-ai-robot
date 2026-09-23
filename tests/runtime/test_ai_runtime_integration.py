"""Milestone 4 必須確認: AI Job running + Button/Core Event → still processed。

AI Job Manager を Runtime Core から隔離した非同期実行にしても、Core が
Button 等の他の Event を AI Job の完了を待たずに処理できることを、
RobotRuntime を通した E2E で証明する。
"""

import json
import tempfile
import unittest
from pathlib import Path

from runtime.action import ActionPlanner, HardwareExecutor
from runtime.adapters.mock import FakeHardwareAdapter
from runtime.ai import AIJob, AIJobManager, AIJobType, FakeAIBackend, new_job_id
from runtime.dispatch import DispatchQueue
from runtime.event import RuntimeEvent
from runtime.models import DecisionType
from runtime.observation import ObservationAdapter
from runtime.reasoner import RuleBasedReasoner
from runtime.robot_logger import JsonlRobotDataLogger
from runtime.robot_runtime import RobotRuntime


def _dispatched_events(dispatch: DispatchQueue, count: int):
    for _ in range(count):
        yield dispatch.pop()


class RecordingLogger:
    def __init__(self):
        self.records = []

    def log(self, record):
        self.records.append(record)

    def close(self):
        pass


class AIJobCoreResponsivenessTest(unittest.TestCase):
    def test_button_event_is_processed_before_slow_ai_job_completes(self):
        dispatch = DispatchQueue()
        adapter = FakeHardwareAdapter()
        backend = FakeAIBackend(default_delay=0.2)
        manager = AIJobManager(backend, dispatch.push_event)
        data_logger = RecordingLogger()

        runtime = RobotRuntime(
            input_source=_dispatched_events(dispatch, count=2),
            adapter=ObservationAdapter(),
            reasoner=RuleBasedReasoner(),
            planner=ActionPlanner(),
            executor=HardwareExecutor(adapter),
            data_logger=data_logger,
        )

        # AI Job (0.2秒かかる) を投入した直後に Button を押す。
        manager.submit(AIJob(new_job_id(), AIJobType.VLM, "fake", None, timeout=2.0))
        dispatch.push_event(RuntimeEvent("BUTTON_PRESSED"))

        count = runtime.run()

        self.assertEqual(count, 2)
        first, second = data_logger.records
        # AI Job の完了を待たされていれば Button が先に Queue へ積まれていても
        # 実処理の順序が崩れる可能性があるが、Dispatch Queue の FIFO と
        # AI Job Manager の非同期実行により Button が先に処理される。
        self.assertEqual(first.event.type, "BUTTON_PRESSED")
        self.assertEqual(first.decision.type, DecisionType.BUTTON_ACKNOWLEDGED)
        self.assertEqual(second.event.type, "AI_RESULT")
        self.assertEqual(second.decision.type, DecisionType.AI_RESULT_RECEIVED)

    def test_ai_result_event_is_written_as_valid_jsonl(self):
        dispatch = DispatchQueue()
        backend = FakeAIBackend(default_output="hello world")
        manager = AIJobManager(backend, dispatch.push_event)

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "robot.jsonl"
            runtime = RobotRuntime(
                input_source=_dispatched_events(dispatch, count=1),
                adapter=ObservationAdapter(),
                reasoner=RuleBasedReasoner(),
                planner=ActionPlanner(),
                executor=HardwareExecutor(FakeHardwareAdapter()),
                data_logger=JsonlRobotDataLogger(log_path),
            )
            manager.submit(
                AIJob(new_job_id(), AIJobType.LLM, "fake", None, timeout=2.0)
            )
            runtime.run()
            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["event"]["type"], "AI_RESULT")
        self.assertEqual(record["event"]["payload"]["status"], "COMPLETED")
        self.assertEqual(record["event"]["payload"]["output"], "hello world")
        self.assertIsNone(record["observation"])


if __name__ == "__main__":
    unittest.main()
