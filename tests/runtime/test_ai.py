import threading
import time
import unittest

from runtime.ai import (
    AI_RESULT,
    AIJob,
    AIJobManager,
    AIJobStatus,
    AIJobType,
    FakeAIBackend,
    NpuResourceState,
    new_job_id,
)

SHORT = 0.05
TIMEOUT_MARGIN = 2.0


class EventSink:
    """push_event の代わりに Event を記録するテスト用スタブ。"""

    def __init__(self) -> None:
        self.events = []
        self._lock = threading.Lock()
        self._new_event = threading.Event()

    def __call__(self, event) -> None:
        with self._lock:
            self.events.append(event)
        self._new_event.set()

    def wait_for(self, count: int, timeout: float = 2.0) -> list:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if len(self.events) >= count:
                    return list(self.events)
            self._new_event.wait(timeout=0.01)
            self._new_event.clear()
        raise AssertionError(f"timed out waiting for {count} events; got {self.events}")


def job(job_type=AIJobType.VLM, timeout=1.0, job_id=None) -> AIJob:
    return AIJob(
        job_id=job_id or new_job_id(),
        type=job_type,
        backend="fake",
        input=None,
        timeout=timeout,
    )


class FakeAIBackendTest(unittest.TestCase):
    def test_immediate_success(self):
        backend = FakeAIBackend(default_output="hello")
        result = backend.run(job())
        self.assertEqual(result, "hello")

    def test_delayed_success(self):
        backend = FakeAIBackend(default_delay=SHORT, default_output="hello")
        start = time.monotonic()
        result = backend.run(job())
        self.assertGreaterEqual(time.monotonic() - start, SHORT)
        self.assertEqual(result, "hello")

    def test_failure(self):
        j = job()
        backend = FakeAIBackend(fail_job_ids=frozenset({j.job_id}))
        with self.assertRaises(RuntimeError):
            backend.run(j)


class AIJobManagerLifecycleTest(unittest.TestCase):
    def test_immediate_success_produces_completed_ai_result_event(self):
        sink = EventSink()
        manager = AIJobManager(FakeAIBackend(default_output="hi"), sink)

        j = job()
        manager.submit(j)

        events = sink.wait_for(1)
        self.assertEqual(events[0].type, AI_RESULT)
        result = events[0].payload
        self.assertEqual(result.job_id, j.job_id)
        self.assertEqual(result.status, AIJobStatus.COMPLETED)
        self.assertEqual(result.output, "hi")

    def test_delayed_success_eventually_completes(self):
        sink = EventSink()
        manager = AIJobManager(FakeAIBackend(default_delay=SHORT), sink)

        j = job(timeout=2.0)
        manager.submit(j)

        events = sink.wait_for(1)
        self.assertEqual(events[0].payload.status, AIJobStatus.COMPLETED)

    def test_backend_exception_produces_failed_result(self):
        sink = EventSink()
        j = job()
        manager = AIJobManager(
            FakeAIBackend(fail_job_ids=frozenset({j.job_id})), sink
        )

        manager.submit(j)

        events = sink.wait_for(1)
        self.assertEqual(events[0].payload.status, AIJobStatus.FAILED)
        self.assertIn(j.job_id, events[0].payload.detail)

    def test_hanging_backend_produces_timeout_result_without_waiting_for_backend(self):
        sink = EventSink()
        j = job(timeout=SHORT)
        manager = AIJobManager(FakeAIBackend(hang_job_ids=frozenset({j.job_id})), sink)

        start = time.monotonic()
        manager.submit(j)
        events = sink.wait_for(1, timeout=SHORT + TIMEOUT_MARGIN)
        elapsed = time.monotonic() - start

        self.assertEqual(events[0].payload.status, AIJobStatus.TIMEOUT)
        # backend の hang (job.timeout + 10秒) を待たず、timeout 通りに確定する。
        self.assertLess(elapsed, SHORT + TIMEOUT_MARGIN)

    def test_timeout_and_late_backend_completion_do_not_double_report(self):
        sink = EventSink()
        j = job(timeout=SHORT)
        # hang ではなく「timeout よりわずかに遅れて成功する」ケース。
        manager = AIJobManager(
            FakeAIBackend(delays={j.job_id: SHORT + 0.2}, default_output="late"),
            sink,
        )

        manager.submit(j)
        events = sink.wait_for(1, timeout=SHORT + TIMEOUT_MARGIN)
        # backend が実際に完了するまで待ってから、Event が増えていないことを確認する。
        time.sleep(0.4)

        self.assertEqual(len(sink.events), 1)
        self.assertEqual(events[0].payload.status, AIJobStatus.TIMEOUT)


class AIJobManagerBackpressureTest(unittest.TestCase):
    def test_same_type_pending_replaces_previous_pending(self):
        sink = EventSink()
        backend = FakeAIBackend(default_delay=SHORT)
        manager = AIJobManager(backend, sink)

        first = job(job_type=AIJobType.STT, timeout=2.0)
        second = job(job_type=AIJobType.STT, timeout=2.0)
        third = job(job_type=AIJobType.STT, timeout=2.0)

        manager.submit(first)
        manager.submit(second)  # pending になる
        manager.submit(third)  # pending を置換、second は実行されない

        events = sink.wait_for(2, timeout=2.0)
        completed_ids = [e.payload.job_id for e in events]

        self.assertEqual(completed_ids, [first.job_id, third.job_id])
        self.assertNotIn(second.job_id, completed_ids)

    def test_different_job_types_run_concurrently_without_blocking_each_other(self):
        sink = EventSink()
        slow_id = new_job_id()
        fast_id = new_job_id()
        backend = FakeAIBackend(delays={slow_id: 0.3, fast_id: SHORT})
        manager = AIJobManager(backend, sink)

        slow = AIJob(slow_id, AIJobType.STT, "fake", None, timeout=2.0)
        fast = AIJob(fast_id, AIJobType.VLM, "fake", None, timeout=2.0)

        manager.submit(slow)
        manager.submit(fast)

        events = sink.wait_for(2, timeout=2.0)
        # type が異なるため、fast (VLM) が slow (STT) を待たず先に完了する。
        self.assertEqual(events[0].payload.job_id, fast_id)
        self.assertEqual(events[1].payload.job_id, slow_id)

    def test_status_reports_running_then_queued_for_pending(self):
        sink = EventSink()
        backend = FakeAIBackend(default_delay=0.2)
        manager = AIJobManager(backend, sink)

        running = job(job_type=AIJobType.LLM, timeout=2.0)
        pending = job(job_type=AIJobType.LLM, timeout=2.0)

        manager.submit(running)
        manager.submit(pending)

        self.assertEqual(manager.status(running.job_id), AIJobStatus.RUNNING)
        self.assertEqual(manager.status(pending.job_id), AIJobStatus.QUEUED)
        self.assertIsNone(manager.status("unknown"))

        sink.wait_for(2, timeout=2.0)


class NpuResourceStateTest(unittest.TestCase):
    def test_free_when_idle_and_exclusive_while_any_job_running(self):
        sink = EventSink()
        backend = FakeAIBackend(default_delay=0.2)
        manager = AIJobManager(backend, sink)
        self.assertEqual(manager.npu_state(), NpuResourceState.FREE)

        manager.submit(job(job_type=AIJobType.STT, timeout=2.0))
        manager.submit(job(job_type=AIJobType.VLM, timeout=2.0))
        self.assertEqual(manager.npu_state(), NpuResourceState.EXCLUSIVE_AI)

        sink.wait_for(2, timeout=2.0)
        self.assertEqual(manager.npu_state(), NpuResourceState.FREE)


if __name__ == "__main__":
    unittest.main()
