"""AI Job (STT/VLM/LLM) の非同期実行基盤 (Milestone 4)。

実 NPU を使わない Fake Backend で、AI Job の非同期性・timeout・failure・
backpressure を検証できるようにする。Runtime Core は同期のままとし、
AI Job Manager / Worker は Core から隔離する (#15.2)。AI Result は Event
として Runtime へ返す (#14, #17)。

最初は本ファイル1つの最小構成とする。責務が増えた時点で
ai_job.py / ai_manager.py / npu_arbiter.py 等へ分割する (#9)。
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .event import RuntimeEvent

logger = logging.getLogger(__name__)

AI_RESULT = "AI_RESULT"


def new_job_id() -> str:
    return uuid.uuid4().hex


class AIJobType(str, Enum):
    STT = "STT"
    VLM = "VLM"
    LLM = "LLM"


class AIJobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    # NpuArbiter が NPU を割り当てず、worker を起動しなかった (Milestone 9, Issue #9)。
    REJECTED = "REJECTED"
    # CANCELLED は Phase 0.8 では実装しない (#14)。


@dataclass(frozen=True)
class AIJob:
    job_id: str
    type: AIJobType
    backend: str
    input: object
    timeout: float
    # Priority Queue / Preemption は実装しない。data model 上の metadata のみ。
    priority: int = 0


@dataclass(frozen=True)
class AIResult:
    job_id: str
    type: AIJobType
    status: AIJobStatus
    output: object = None
    detail: str | None = None


class AIBackendTimeout(Exception):
    """Backend 自身が timeout を検出し、worker を終了・回収したことを表す。"""


class AIBackend(Protocol):
    def run(self, job: AIJob) -> object:
        """Job を実行して出力を返す。戻った時点で NPU を使う処理は終了している
        こと (#15.3)。timeout は `AIBackendTimeout` で知らせる。"""
        ...

    def shutdown(self) -> None:
        """実行中の処理を終了させる。Runtime 停止時に呼ばれる。"""
        ...


class FakeAIBackend:
    """テスト用 Backend。immediate success / delayed success / failure /
    timeout (hang) を job_id 単位で再現する。"""

    def __init__(
        self,
        default_delay: float = 0.0,
        default_output: object = "ok",
        fail_job_ids: frozenset[str] = frozenset(),
        hang_job_ids: frozenset[str] = frozenset(),
        delays: dict[str, float] | None = None,
    ) -> None:
        self._default_delay = default_delay
        self._default_output = default_output
        self._fail_job_ids = fail_job_ids
        self._hang_job_ids = hang_job_ids
        self._delays = delays or {}

    def run(self, job: AIJob) -> object:
        if job.job_id in self._hang_job_ids:
            # timeout 再現用。テストの timeout より十分長く応答しない。
            time.sleep(job.timeout + 10)
            return self._default_output
        delay = self._delays.get(job.job_id, self._default_delay)
        if delay:
            time.sleep(delay)
        if job.job_id in self._fail_job_ids:
            raise RuntimeError(f"fake backend failure for job {job.job_id}")
        return self._default_output

    def shutdown(self) -> None:
        pass


class SubprocessAIBackend:
    """Job ごとに worker process を起動する実 Backend (#15.3, Milestone 7)。

    worker は stdout の最後の行に JSON object を1つ出力して終了する契約とし、
    その object を AI Result の output とする。timeout / shutdown 時は worker を
    terminate / kill し、wait (reap) まで完了してから戻る。これにより
    `AIJobManager` は前 Job の worker が終了してから次 Job を開始できる。

    worker 側は hailo-apps venv の Python で実行し、Runtime プロセスには
    hailo_platform / OpenCV 等の依存を持ち込まない。
    """

    _TERMINATE_GRACE_SEC = 5.0
    _STDERR_TAIL = 500

    def __init__(self, command: list[str]) -> None:
        self._command = list(command)
        self._lock = threading.Lock()
        self._procs: set[subprocess.Popen] = set()
        self._closed = False

    def run(self, job: AIJob) -> object:
        # 「閉じているかの確認 → 起動 → 登録」を1つの lock の中で行う。shutdown が
        # 生成直後・登録前の worker を見落とすことや、shutdown 後に新しい worker を
        # 起動することを防ぐ (PR #10 review [P1])。
        with self._lock:
            if self._closed:
                raise RuntimeError("AI backend is shut down; worker not started")
            proc = subprocess.Popen(
                self._command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # 端末の Ctrl+C (SIGINT) を worker に直接届けない。実機で、推論中の
                # HailoRT が SIGINT による EINTR で abort した。worker の停止は
                # Runtime が管理する (#15.3)。worker は新しいプロセスグループの
                # リーダーになるため、停止はグループ単位で行える。
                start_new_session=True,
            )
            self._procs.add(proc)
        try:
            try:
                stdout, stderr = proc.communicate(timeout=job.timeout)
            except subprocess.TimeoutExpired:
                self._signal_group(proc, force=True)
                proc.communicate()  # reap
                raise AIBackendTimeout(
                    f"worker killed after {job.timeout:g}s (pid={proc.pid})"
                ) from None
        finally:
            with self._lock:
                self._procs.discard(proc)

        if proc.returncode != 0:
            raise RuntimeError(
                f"worker exited with {proc.returncode}: "
                f"{stderr.strip()[-self._STDERR_TAIL:]}"
            )
        return _parse_worker_output(stdout)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            procs = list(self._procs)
        for proc in procs:
            self._signal_group(proc, force=False)
        for proc in procs:
            # worker はモデルロード等の native 呼び出し中は SIGTERM にすぐ応答できない。
            # 止まって見えないよう待機を通知し、待機中の Ctrl+C は即時 kill として扱う。
            logger.info(
                "Stopping AI worker (pid=%d, up to %gs; press Ctrl+C again to kill)",
                proc.pid,
                self._TERMINATE_GRACE_SEC,
            )
            try:
                proc.wait(timeout=self._TERMINATE_GRACE_SEC)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                self._signal_group(proc, force=True)
                proc.wait()
                logger.info("AI worker killed (pid=%d)", proc.pid)
            # worker 本体が終わっても、SIGTERM に応じない子 (rpicam-still 等) が
            # グループに残り得るため、最後にグループ全体を強制終了する。
            self._kill_remaining_group(proc)

    def _signal_group(self, proc: subprocess.Popen, force: bool) -> None:
        """worker とその子 (撮影用の rpicam-still 等) をまとめて停止する
        (PR #10 review [P2])。

        worker は start_new_session=True で起動しているため、POSIX では
        プロセスグループ ID が worker の PID と一致する。プロセスグループの無い
        環境 (開発 PC の Windows) では worker 本体だけを停止する。
        """
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL if force else signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif force:
            proc.kill()
        else:
            proc.terminate()

    def _kill_remaining_group(self, proc: subprocess.Popen) -> None:
        if os.name != "posix":
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _parse_worker_output(stdout: str) -> object:
    # HailoRT 等のライブラリが stdout へログを出す可能性があるため、
    # 最後の JSON object 行を結果とする。
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(f"worker produced no JSON result: {stdout.strip()[-200:]!r}")


class NpuResourceState(str, Enum):
    """#16.2 NPU Arbiter Boundary の概念状態。"""

    FREE = "FREE"
    VISION = "VISION"
    EXCLUSIVE_AI = "EXCLUSIVE_AI"


class NpuMode(str, Enum):
    """起動時に明示する NPU の運用モード (Milestone 9, Issue #9)。"""

    # Vision (rpicam-apps の YOLO) が NPU を使う。AI Job は拒否する。
    VISION = "vision"
    # Vision を使わず、Runtime 管理下の AI Job が NPU を排他的に使う。
    AI = "ai"


class NpuArbiter:
    """Runtime 管理下の NPU Job に対する admission control / resource visibility。

    Milestone 8 の実機確認で、rpicam-apps (既定の UNIQUE VDevice) と VLM は NPU を
    同時に使えないことがわかった (Issue #9)。NPU の状態は JSONL の到着間隔から
    推定せず、起動時に明示されたモードで決める。

    これは OS / HailoRT レベルのロックではない。Runtime の外で手動起動された
    rpicam-hello 等による NPU の利用は防げない。
    """

    def __init__(self, mode: NpuMode) -> None:
        self._lock = threading.Lock()
        self._mode = mode
        self._owner_job_id: str | None = None
        self._state = (
            NpuResourceState.VISION if mode is NpuMode.VISION else NpuResourceState.FREE
        )
        logger.info("NPU mode: %s (state=%s)", mode.value, self._state.value)

    @property
    def mode(self) -> NpuMode:
        return self._mode

    def state(self) -> NpuResourceState:
        with self._lock:
            return self._state

    def try_acquire(self, job_id: str) -> str | None:
        """NPU を Job に割り当てる。割り当てたら None、拒否したら理由を返す。"""
        with self._lock:
            if self._state is NpuResourceState.VISION:
                return "NPU is reserved for VISION (--npu-mode vision)"
            if self._state is NpuResourceState.EXCLUSIVE_AI:
                return f"NPU is in use by AI job {self._owner_job_id}"
            self._state = NpuResourceState.EXCLUSIVE_AI
            self._owner_job_id = job_id
        logger.info("NPU FREE -> EXCLUSIVE_AI (job=%s)", job_id)
        return None

    def release(self, job_id: str) -> None:
        """Job の worker が終了 (reap) した後に呼ぶ (#15.3)。"""
        with self._lock:
            if self._owner_job_id != job_id:
                return
            self._state = NpuResourceState.FREE
            self._owner_job_id = None
        logger.info("NPU EXCLUSIVE_AI -> FREE (job=%s)", job_id)


@dataclass
class _TypeState:
    running: AIJob | None = None
    pending: AIJob | None = None


class AIJobManager:
    """同一 Job Type につき running 最大1件 + pending 最新1件 (#17)。

    pending 中に新しい同種 request が来た場合は pending を置換する
    (古い pending job は実行されない)。Job の開始時に NpuArbiter から NPU を
    獲得し、獲得できなければ worker を起動せず REJECTED を返す。異なる Job Type
    の Job も、NPU が EXCLUSIVE_AI の間は拒否される (AC-NPU-01)。
    Priority Queue / Preemption / Starvation control / Generic scheduler は
    実装しない。
    """

    def __init__(
        self,
        backend: AIBackend,
        push_event: Callable[[RuntimeEvent], None],
        arbiter: NpuArbiter | None = None,
    ) -> None:
        self._backend = backend
        self._push_event = push_event
        self._arbiter = arbiter or NpuArbiter(NpuMode.AI)
        self._lock = threading.Lock()
        self._type_state: dict[AIJobType, _TypeState] = {}
        self._shutting_down = False

    def npu_state(self) -> NpuResourceState:
        return self._arbiter.state()

    def status(self, job_id: str) -> AIJobStatus | None:
        """QUEUED / RUNNING の間だけ問い合わせ可能。完了後や未知の job_id は
        None を返す (完了結果は AI_RESULT Event を参照する) (AC-AI-02)。"""
        with self._lock:
            for state in self._type_state.values():
                if state.running is not None and state.running.job_id == job_id:
                    return AIJobStatus.RUNNING
                if state.pending is not None and state.pending.job_id == job_id:
                    return AIJobStatus.QUEUED
        return None

    def submit(self, job: AIJob) -> None:
        with self._lock:
            if self._shutting_down:
                logger.warning("AI Job rejected during shutdown: %s", job.job_id)
                return
            state = self._type_state.setdefault(job.type, _TypeState())
            if state.running is None:
                state.running = job
                start_now = True
            else:
                state.pending = job  # 既存 pending があれば置換
                start_now = False
        if start_now:
            self._start(job)

    def shutdown(self) -> None:
        """新規 Job と pending Job を破棄し、実行中の backend 処理を終了させる。

        shutdown 後は AI_RESULT Event を出さない (Runtime は既に停止している)。
        """
        with self._lock:
            self._shutting_down = True
            for state in self._type_state.values():
                state.pending = None
        self._backend.shutdown()

    def _emit(self, result: AIResult) -> None:
        # shutdown 後は Event を出さない (Runtime は既に停止している)。
        with self._lock:
            if self._shutting_down:
                return
        self._push_event(RuntimeEvent(AI_RESULT, payload=result))

    def _start(self, job: AIJob) -> None:
        reason = self._arbiter.try_acquire(job.job_id)
        if reason is not None:
            logger.warning("AI Job rejected: %s (%s)", job.job_id, reason)
            self._emit(AIResult(job.job_id, job.type, AIJobStatus.REJECTED, detail=reason))
            self._on_job_finished(job)
            return

        state_lock = threading.Lock()
        reported = False
        timer_holder: list[threading.Timer] = []

        def report(result: AIResult) -> None:
            # timeout と backend 完了の競合で二重に Event を出さない。
            nonlocal reported
            with state_lock:
                if reported:
                    return
                reported = True
            if timer_holder:
                timer_holder[0].cancel()
            self._emit(result)

        def worker() -> None:
            try:
                output = self._backend.run(job)
            except AIBackendTimeout as exc:
                logger.warning("AI Job timeout (backend): %s (%s)", job.job_id, exc)
                report(AIResult(job.job_id, job.type, AIJobStatus.TIMEOUT, detail=str(exc)))
            except Exception as exc:  # noqa: BLE001 - Event 経由で伝える
                logger.warning("AI Job failed: %s (%s)", job.job_id, exc)
                report(AIResult(job.job_id, job.type, AIJobStatus.FAILED, detail=str(exc)))
            else:
                report(AIResult(job.job_id, job.type, AIJobStatus.COMPLETED, output=output))
            finally:
                # backend が戻った = worker が終了 (reap) した後でのみ NPU と実行枠を
                # 解放し、次の pending Job を開始する (#15.3)。timeout を検出した
                # 時点では解放しない。
                self._arbiter.release(job.job_id)
                self._on_job_finished(job)

        def on_timeout() -> None:
            logger.warning("AI Job timeout: %s", job.job_id)
            report(AIResult(job.job_id, job.type, AIJobStatus.TIMEOUT, detail="timeout"))

        timer = threading.Timer(job.timeout, on_timeout)
        timer.daemon = True
        timer_holder.append(timer)
        timer.start()
        threading.Thread(target=worker, daemon=True).start()

    def _on_job_finished(self, job: AIJob) -> None:
        next_job: AIJob | None = None
        with self._lock:
            state = self._type_state[job.type]
            state.running = None
            if state.pending is not None and not self._shutting_down:
                next_job = state.pending
                state.pending = None
                state.running = next_job
        if next_job is not None:
            self._start(next_job)
