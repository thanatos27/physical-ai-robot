"""AI Job (STT/VLM/LLM) の非同期実行基盤 (Milestone 4)。

実 NPU を使わない Fake Backend で、AI Job の非同期性・timeout・failure・
backpressure を検証できるようにする。Runtime Core は同期のままとし、
AI Job Manager / Worker は Core から隔離する (#15.2)。AI Result は Event
として Runtime へ返す (#14, #17)。

最初は本ファイル1つの最小構成とする。責務が増えた時点で
ai_job.py / ai_manager.py / npu_arbiter.py 等へ分割する (#9)。
"""

from __future__ import annotations

import logging
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


class AIBackend(Protocol):
    def run(self, job: AIJob) -> object: ...


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


class NpuResourceState(str, Enum):
    """#16.2 NPU Arbiter Boundary の概念状態。

    Milestone 4 時点の AIJobManager は自身が起動した AI Job の実行有無しか
    把握できない (Runtime 外の rpicam-apps / YOLO の Hailo 利用は見えない)。
    したがって VISION はここでは一度も設定しない。Vision との実際の排他制御は
    Milestone 8 (実機での共存検証) の結果を踏まえて Milestone 9 で決定する
    (AC-NPU-04: 見かけだけの Lock にしない)。
    """

    FREE = "FREE"
    VISION = "VISION"
    EXCLUSIVE_AI = "EXCLUSIVE_AI"


@dataclass
class _TypeState:
    running: AIJob | None = None
    pending: AIJob | None = None


class AIJobManager:
    """同一 Job Type につき running 最大1件 + pending 最新1件 (#17)。

    pending 中に新しい同種 request が来た場合は pending を置換する
    (古い pending job は実行されない)。異なる Job Type 同士は互いに
    ブロックしない。Priority Queue / Preemption / Starvation control /
    Generic scheduler は実装しない。
    """

    def __init__(
        self,
        backend: AIBackend,
        push_event: Callable[[RuntimeEvent], None],
    ) -> None:
        self._backend = backend
        self._push_event = push_event
        self._lock = threading.Lock()
        self._type_state: dict[AIJobType, _TypeState] = {}
        self._running_job_ids: set[str] = set()

    def npu_state(self) -> NpuResourceState:
        with self._lock:
            return (
                NpuResourceState.EXCLUSIVE_AI
                if self._running_job_ids
                else NpuResourceState.FREE
            )

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
            state = self._type_state.setdefault(job.type, _TypeState())
            if state.running is None:
                state.running = job
                self._running_job_ids.add(job.job_id)
                start_now = True
            else:
                state.pending = job  # 既存 pending があれば置換
                start_now = False
        if start_now:
            self._start(job)

    def _start(self, job: AIJob) -> None:
        state_lock = threading.Lock()
        finalized = False
        timer_holder: list[threading.Timer] = []

        def finalize(result: AIResult) -> None:
            nonlocal finalized
            with state_lock:
                if finalized:
                    return  # timeout と正常完了の競合を防ぎ、二重に Event を出さない。
                finalized = True
            if timer_holder:
                timer_holder[0].cancel()
            self._push_event(RuntimeEvent(AI_RESULT, payload=result))
            self._on_job_finished(job)

        def worker() -> None:
            try:
                output = self._backend.run(job)
            except Exception as exc:  # noqa: BLE001 - Event 経由で伝える
                logger.warning("AI Job failed: %s (%s)", job.job_id, exc)
                finalize(
                    AIResult(job.job_id, job.type, AIJobStatus.FAILED, detail=str(exc))
                )
                return
            finalize(
                AIResult(job.job_id, job.type, AIJobStatus.COMPLETED, output=output)
            )

        def on_timeout() -> None:
            logger.warning("AI Job timeout: %s", job.job_id)
            finalize(
                AIResult(job.job_id, job.type, AIJobStatus.TIMEOUT, detail="timeout")
            )

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
            self._running_job_ids.discard(job.job_id)
            if state.pending is not None:
                next_job = state.pending
                state.pending = None
                state.running = next_job
                self._running_job_ids.add(next_job.job_id)
        if next_job is not None:
            self._start(next_job)
