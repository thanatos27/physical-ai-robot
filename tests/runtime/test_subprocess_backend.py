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
        # FakeProc の pid は実在しないため、os.killpg を呼ばないよう差し替える
        # (Raspberry Pi 上で無関係なプロセスグループへ送らないため)。
        backend._signal_group = lambda p, force: p.kill() if force else p.terminate()
        backend._kill_remaining_group = lambda p: p.calls.append("kill_group")
        return backend

    def test_unresponsive_worker_is_killed_after_grace_period(self):
        import subprocess

        proc = FakeProc([subprocess.TimeoutExpired("worker", 5), None])
        backend = self._backend_with(proc)

        with self.assertLogs("runtime.ai", level="INFO") as logs:
            backend.shutdown()

        self.assertEqual(
            proc.calls,
            [
                "terminate",
                ("wait", SubprocessAIBackend._TERMINATE_GRACE_SEC),
                "kill",
                ("wait", None),
                "kill_group",
            ],
        )
        self.assertIn("Stopping AI worker", "\n".join(logs.output))

    def test_second_ctrl_c_during_wait_kills_without_raising(self):
        proc = FakeProc([KeyboardInterrupt(), None])
        backend = self._backend_with(proc)

        with self.assertLogs("runtime.ai", level="INFO"):
            backend.shutdown()  # KeyboardInterrupt を外へ出さない

        self.assertEqual(proc.calls[-3:], ["kill", ("wait", None), "kill_group"])


class SubprocessAIBackendSpawnRaceTest(unittest.TestCase):
    """PR #10 review [P1]: worker の起動・登録と shutdown を同期する。"""

    def test_run_after_shutdown_does_not_start_a_worker(self):
        from unittest import mock

        backend = SubprocessAIBackend(python("import time; time.sleep(30)"))
        backend.shutdown()

        with mock.patch("runtime.ai.subprocess.Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "shut down"):
                backend.run(job())

        popen.assert_not_called()

    def test_shutdown_during_spawn_waits_for_registration_and_stops_the_worker(self):
        import subprocess
        from unittest import mock

        real_popen = subprocess.Popen
        spawned = threading.Event()
        proceed = threading.Event()
        created = []

        def slow_popen(*args, **kwargs):
            # 生成直後・登録前で止め、その間に shutdown を呼ぶ。
            proc = real_popen(*args, **kwargs)
            created.append(proc)
            spawned.set()
            proceed.wait(timeout=10)
            return proc

        backend = SubprocessAIBackend(python("import time; time.sleep(30)"))
        errors = []

        def run():
            try:
                backend.run(job(timeout=30))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        with mock.patch("runtime.ai.subprocess.Popen", side_effect=slow_popen):
            runner = threading.Thread(target=run)
            runner.start()
            self.assertTrue(spawned.wait(timeout=10))

            stopper = threading.Thread(target=backend.shutdown)
            stopper.start()
            time.sleep(0.3)
            # 登録が終わるまで shutdown は lock で待たされ、worker を見落とさない。
            self.assertTrue(stopper.is_alive())

            proceed.set()
            stopper.join(timeout=15)
            runner.join(timeout=15)

        self.assertFalse(stopper.is_alive())
        self.assertFalse(runner.is_alive())
        self.assertIsNotNone(created[0].poll())  # worker は停止・回収済み
        self.assertEqual(len(errors), 1)


class AIJobManagerShutdownRaceTest(unittest.TestCase):
    """PR #10 review [P1]: pending Job の選択から _start() までの間に shutdown が
    来ても、worker を起動しない。"""

    def test_pending_job_selected_before_shutdown_does_not_start_a_worker(self):
        import subprocess
        from unittest import mock

        from runtime.ai import AIJobManager

        real_popen = subprocess.Popen
        popen_calls = []

        def counting_popen(*args, **kwargs):
            popen_calls.append(args)
            return real_popen(*args, **kwargs)

        # first が実行中に second を submit して pending にするため、first の worker は
        # すぐには終わらないようにする。
        backend = SubprocessAIBackend(
            python('import time; time.sleep(0.5); print(\'{"output": "x"}\')')
        )
        manager = AIJobManager(backend, lambda event: None)
        original_start = manager._start
        second_selected = threading.Event()
        shutdown_done = threading.Event()

        def start(next_job):
            if next_job is not first:
                # _on_job_finished() が pending Job を選んだ直後で止め、shutdown を待つ。
                second_selected.set()
                shutdown_done.wait(timeout=10)
            original_start(next_job)

        first = job(timeout=10)
        second = job(timeout=10)
        with mock.patch("runtime.ai.subprocess.Popen", side_effect=counting_popen), \
                mock.patch.object(manager, "_start", side_effect=start):
            manager.submit(first)
            manager.submit(second)  # pending
            self.assertTrue(second_selected.wait(timeout=10))

            manager.shutdown()
            shutdown_done.set()
            time.sleep(0.5)

        self.assertEqual(len(popen_calls), 1)  # first の worker だけ


GRANDCHILD_WORKER = """
import pathlib, subprocess, sys, time
child = subprocess.Popen(
    [sys.executable, "-c",
     "import pathlib, sys, time; time.sleep(1.5); pathlib.Path(sys.argv[1]).write_text('alive')",
     {marker!r}],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pathlib.Path({started!r}).write_text(str(child.pid))
time.sleep(30)
"""


@unittest.skipUnless(hasattr(__import__("os"), "killpg"), "process groups require POSIX")
class SubprocessAIBackendChildProcessTest(unittest.TestCase):
    """PR #10 review [P2]: worker が起動した子 (撮影用の rpicam-still 等) も停止する。"""

    def _backend(self, tmp):
        from pathlib import Path

        marker = Path(tmp) / "child_survived"
        started = Path(tmp) / "child_started"
        code = GRANDCHILD_WORKER.format(marker=str(marker), started=str(started))
        return SubprocessAIBackend(python(code)), marker, started

    def _wait_for(self, path, timeout=10.0):
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        return path.exists()

    def test_shutdown_stops_the_workers_children(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            backend, marker, started = self._backend(tmp)
            runner = threading.Thread(target=lambda: self._run_ignoring_errors(backend, 30))
            runner.start()
            self.assertTrue(self._wait_for(started))

            backend.shutdown()
            runner.join(timeout=15)
            time.sleep(2.5)  # 子が生きていれば 1.5 秒後に marker を作る

            self.assertFalse(marker.exists())

    def test_timeout_stops_the_workers_children(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            backend, marker, started = self._backend(tmp)

            with self.assertRaises(AIBackendTimeout):
                backend.run(job(timeout=1.0))
            self.assertTrue(started.exists())
            time.sleep(2.5)

            self.assertFalse(marker.exists())

    @staticmethod
    def _run_ignoring_errors(backend, timeout):
        try:
            backend.run(job(timeout=timeout))
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    unittest.main()
