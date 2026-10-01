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


if __name__ == "__main__":
    unittest.main()
