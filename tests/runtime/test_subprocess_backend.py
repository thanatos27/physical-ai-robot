import sys
import threading
import time
import unittest

from runtime.ai import AIBackendTimeout, AIJob, AIJobType, SubprocessAIBackend, new_job_id


def job(timeout=5.0):
    return AIJob(new_job_id(), AIJobType.VLM, "subprocess", None, timeout=timeout)


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


class SubprocessAIBackendTest(unittest.TestCase):
    def test_returns_last_json_line_as_output(self):
        backend = SubprocessAIBackend(
            python('print("library log line"); print(\'{"output": "a mouse"}\')')
        )

        self.assertEqual(backend.run(job()), {"output": "a mouse"})

    def test_nonzero_exit_raises_with_stderr_tail(self):
        backend = SubprocessAIBackend(
            python('import sys; sys.stderr.write("camera busy"); sys.exit(3)')
        )

        with self.assertRaisesRegex(RuntimeError, "exited with 3.*camera busy"):
            backend.run(job())

    def test_missing_json_raises(self):
        backend = SubprocessAIBackend(python('print("no json here")'))

        with self.assertRaisesRegex(RuntimeError, "no JSON result"):
            backend.run(job())

    def test_worker_is_started_in_its_own_session(self):
        # 端末の Ctrl+C (SIGINT) が worker に直接届かないこと (実機で HailoRT が
        # SIGINT による EINTR で abort したため)。
        from unittest import mock

        backend = SubprocessAIBackend(python('print(\'{"output": "x"}\')'))
        with mock.patch("runtime.ai.subprocess.Popen", wraps=__import__("subprocess").Popen) as popen:
            backend.run(job())

        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_timeout_kills_and_reaps_worker_before_returning(self):
        backend = SubprocessAIBackend(python("import time; time.sleep(30)"))

        start = time.monotonic()
        with self.assertRaises(AIBackendTimeout):
            backend.run(job(timeout=0.3))
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 10.0)
        # 戻った時点で worker は回収済み (追跡中の process が残っていない)。
        self.assertEqual(backend._procs, set())

    def test_shutdown_terminates_running_worker(self):
        backend = SubprocessAIBackend(python("import time; time.sleep(30)"))
        errors = []

        def run():
            try:
                backend.run(job(timeout=30.0))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        deadline = time.monotonic() + 5.0
        while not backend._procs and time.monotonic() < deadline:
            time.sleep(0.01)

        backend.shutdown()
        thread.join(timeout=10.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)


class FakeProc:
    """terminate に応答しない worker (native 呼び出し中) を模擬する。"""

    pid = 4242

    def __init__(self, wait_side_effect):
        self.calls = []
        self._wait_side_effect = list(wait_side_effect)

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")

    def wait(self, timeout=None):
        self.calls.append(("wait", timeout))
        if self._wait_side_effect:
            effect = self._wait_side_effect.pop(0)
            if effect is not None:
                raise effect
        return 0


class SubprocessAIBackendShutdownTest(unittest.TestCase):
    def _backend_with(self, proc):
        backend = SubprocessAIBackend(["unused"])
        backend._procs.add(proc)
        return backend

    def test_unresponsive_worker_is_killed_after_grace_period(self):
        import subprocess

        proc = FakeProc([subprocess.TimeoutExpired("worker", 5), None])
        backend = self._backend_with(proc)

        with self.assertLogs("runtime.ai", level="INFO") as logs:
            backend.shutdown()

        self.assertEqual(
            proc.calls,
            ["terminate", ("wait", SubprocessAIBackend._TERMINATE_GRACE_SEC), "kill", ("wait", None)],
        )
        self.assertIn("Stopping AI worker", "\n".join(logs.output))

    def test_second_ctrl_c_during_wait_kills_without_raising(self):
        proc = FakeProc([KeyboardInterrupt(), None])
        backend = self._backend_with(proc)

        with self.assertLogs("runtime.ai", level="INFO"):
            backend.shutdown()  # KeyboardInterrupt を外へ出さない

        self.assertIn("kill", proc.calls)
        self.assertEqual(proc.calls[-1], ("wait", None))


if __name__ == "__main__":
    unittest.main()
