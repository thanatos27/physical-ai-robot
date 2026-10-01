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

    def test_different_job_type_is_rejected_while_npu_is_exclusive(self):
        # Milestone 9 (Issue #9): NPU は EXCLUSIVE_AI の間、type が異なる Job にも
        # 割り当てない (AC-NPU-01)。Milestone 4 では異なる type は同時に実行していた。
        sink = EventSink()
        backend = BlockingBackend()
        manager = AIJobManager(backend, sink)
        running = AIJob(new_job_id(), AIJobType.STT, "fake", None, timeout=2.0)
        other = AIJob(new_job_id(), AIJobType.VLM, "fake", None, timeout=2.0)

        manager.submit(running)
        manager.submit(other)
        events = sink.wait_for(1)

        self.assertEqual(events[0].payload.job_id, other.job_id)
        self.assertEqual(events[0].payload.status, AIJobStatus.REJECTED)
        self.assertIn(running.job_id, events[0].payload.detail)
        # 拒否された Job の worker は起動されない。
        self.assertEqual(backend.started, [running.job_id])

        backend.release()
        sink.wait_for(2)
        self.assertEqual(sink.events[1].payload.status, AIJobStatus.COMPLETED)

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


class BlockingBackend:
    """run() が release() されるまで戻らない backend (NPU を掴んだままの worker を模擬)。"""

    def __init__(self, raise_on_release=None):
        self.started = []
        self.shutdown_called = False
        self._release = threading.Event()
        self._raise_on_release = raise_on_release
        self._lock = threading.Lock()

    def run(self, job):
        with self._lock:
            self.started.append(job.job_id)
        self._release.wait(timeout=5.0)
        if self._raise_on_release is not None:
            raise self._raise_on_release
        return "done"

    def release(self):
        self._release.set()

    def shutdown(self):
        self.shutdown_called = True
        self.release()


class AIJobManagerWorkerReapTest(unittest.TestCase):
    """#15.3: timeout 後も、前 Job の backend が戻るまで次 Job を開始しない。"""

    def test_pending_job_waits_for_timed_out_backend_to_return(self):
        sink = EventSink()
        backend = BlockingBackend()
        manager = AIJobManager(backend, sink)
        first = job(job_type=AIJobType.VLM, timeout=SHORT)
        second = job(job_type=AIJobType.VLM, timeout=2.0)

        manager.submit(first)
        manager.submit(second)
        events = sink.wait_for(1)

        # TIMEOUT は即座に報告されるが、backend はまだ戻っていない。
        self.assertEqual(events[0].payload.status, AIJobStatus.TIMEOUT)
        time.sleep(0.2)
        self.assertEqual(backend.started, [first.job_id])
        self.assertEqual(manager.status(first.job_id), AIJobStatus.RUNNING)
        self.assertEqual(manager.status(second.job_id), AIJobStatus.QUEUED)
        self.assertEqual(manager.npu_state(), NpuResourceState.EXCLUSIVE_AI)

        backend.release()
        sink.wait_for(2)

        self.assertEqual(backend.started, [first.job_id, second.job_id])
        # 遅れて戻った first の結果は二重に報告されない。
        self.assertEqual(
            [e.payload.job_id for e in sink.events], [first.job_id, second.job_id]
        )

    def test_backend_timeout_is_reported_as_timeout(self):
        from runtime.ai import AIBackendTimeout

        sink = EventSink()
        backend = BlockingBackend(raise_on_release=AIBackendTimeout("worker killed"))
        manager = AIJobManager(backend, sink)
        j = job(timeout=2.0)

        manager.submit(j)
        backend.release()
        events = sink.wait_for(1)

        self.assertEqual(events[0].payload.status, AIJobStatus.TIMEOUT)
        self.assertIn("worker killed", events[0].payload.detail)


class AIJobManagerShutdownTest(unittest.TestCase):
    def test_shutdown_stops_backend_drops_pending_and_emits_no_events(self):
        sink = EventSink()
        backend = BlockingBackend()
        manager = AIJobManager(backend, sink)
        running = job(job_type=AIJobType.VLM, timeout=2.0)
        pending = job(job_type=AIJobType.VLM, timeout=2.0)
        manager.submit(running)
        manager.submit(pending)

        manager.shutdown()
        time.sleep(0.2)

        self.assertTrue(backend.shutdown_called)
        self.assertEqual(backend.started, [running.job_id])
        self.assertEqual(sink.events, [])
        self.assertEqual(manager.npu_state(), NpuResourceState.FREE)

    def test_submit_after_shutdown_is_rejected(self):
        sink = EventSink()
        backend = BlockingBackend()
        manager = AIJobManager(backend, sink)
        manager.shutdown()

        manager.submit(job())
        time.sleep(0.1)

        self.assertEqual(backend.started, [])


class NpuResourceStateTest(unittest.TestCase):
    def test_free_exclusive_free_around_a_job(self):
        sink = EventSink()
        backend = BlockingBackend()
        manager = AIJobManager(backend, sink)
        self.assertEqual(manager.npu_state(), NpuResourceState.FREE)

        manager.submit(job(timeout=2.0))
        self.assertEqual(manager.npu_state(), NpuResourceState.EXCLUSIVE_AI)

        backend.release()
        sink.wait_for(1)
        time.sleep(0.05)
        self.assertEqual(manager.npu_state(), NpuResourceState.FREE)


class NpuArbiterTest(unittest.TestCase):
    def test_vision_mode_reserves_npu_and_rejects_ai(self):
        from runtime.ai import NpuArbiter, NpuMode

        arbiter = NpuArbiter(NpuMode.VISION)

        self.assertEqual(arbiter.state(), NpuResourceState.VISION)
        reason = arbiter.try_acquire("job-1")
        self.assertIn("VISION", reason)
        self.assertEqual(arbiter.state(), NpuResourceState.VISION)

    def test_ai_mode_acquire_and_release(self):
        from runtime.ai import NpuArbiter, NpuMode

        arbiter = NpuArbiter(NpuMode.AI)

        self.assertIsNone(arbiter.try_acquire("job-1"))
        self.assertEqual(arbiter.state(), NpuResourceState.EXCLUSIVE_AI)
        self.assertIn("job-1", arbiter.try_acquire("job-2"))

        arbiter.release("job-2")  # 所有者でない Job の release は無視する
        self.assertEqual(arbiter.state(), NpuResourceState.EXCLUSIVE_AI)

        arbiter.release("job-1")
        self.assertEqual(arbiter.state(), NpuResourceState.FREE)

    def test_transitions_are_logged(self):
        from runtime.ai import NpuArbiter, NpuMode

        with self.assertLogs("runtime.ai", level="INFO") as logs:
            arbiter = NpuArbiter(NpuMode.AI)
            arbiter.try_acquire("job-1")
            arbiter.release("job-1")

        output = "\n".join(logs.output)
        self.assertIn("NPU mode: ai", output)
        self.assertIn("FREE -> EXCLUSIVE_AI (job=job-1)", output)
        self.assertIn("EXCLUSIVE_AI -> FREE (job=job-1)", output)


class VisionModeManagerTest(unittest.TestCase):
    def test_job_is_rejected_without_starting_worker_in_vision_mode(self):
        from runtime.ai import NpuArbiter, NpuMode

        sink = EventSink()
        backend = BlockingBackend()
        manager = AIJobManager(backend, sink, NpuArbiter(NpuMode.VISION))
        j = job()

        manager.submit(j)
        events = sink.wait_for(1)

        result = events[0].payload
        self.assertEqual(result.job_id, j.job_id)
        self.assertEqual(result.status, AIJobStatus.REJECTED)
        self.assertIn("VISION", result.detail)
        self.assertEqual(backend.started, [])
        self.assertIsNone(manager.status(j.job_id))
        self.assertEqual(manager.npu_state(), NpuResourceState.VISION)


if __name__ == "__main__":
    unittest.main()
