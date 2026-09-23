"""複数 Input Source (Vision State, Button / AI Result Event 等) を単一の
Dispatch Queue へ enqueue 順の FIFO で merge する最小 Multiplexer。

Design: docs/specs/phase-0.8-stationary-ai-robot.md #10, #15.2, #17
(FIFO Dispatch + State Coalescing。Issue #2 で論点を提起し PR #3 で確定)

Runtime Core (robot_runtime.py) の同期ループ構造・SIGINT/Shutdown 挙動には
一切変更を加えない。ここで提供するのは Core の手前に置く Input Source のみで、
`RobotRuntime` からは従来通り `Iterator[DetectionEvent]` として見える。
"""

from __future__ import annotations

import threading
from typing import Generic, Iterable, Iterator, TypeVar

from .event import EventQueue, RuntimeEvent
from .models import DetectionEvent

T = TypeVar("T")

_EOF = "__EOF__"
_ERROR = "__ERROR__"


class StateChannel(Generic[T]):
    """State型入力1種類分の「最新値 + 未処理通知は最大1件」を管理する。

    `publish()` での pending 判定 (check-then-act) と、`DispatchQueue` が
    対応する通知を dequeue した際の pending クリアを同じ lock で直列化する
    ことで race condition を避ける (PR #3 レビュー指摘への対応)。

    value の更新は pending 状態に関わらず常に行われ、通知を受け取った側は
    使用する瞬間に `latest()` を読むことを前提とする。これにより、通知が
    coalesce されて1件に間引かれても最新値が失われることはない。
    """

    def __init__(self, notification_type: str, dispatch: "DispatchQueue") -> None:
        self.notification_type = notification_type
        self._dispatch = dispatch
        self._lock = threading.Lock()
        self._value: T | None = None
        self._has_value = False
        self._pending = False

    def publish(self, value: T) -> None:
        with self._lock:
            self._value = value
            self._has_value = True
            already_pending = self._pending
            self._pending = True
        if not already_pending:
            self._dispatch._push(RuntimeEvent(self.notification_type, payload=self))

    def latest(self) -> "T | None":
        with self._lock:
            return self._value if self._has_value else None

    def _clear_pending(self) -> None:
        with self._lock:
            self._pending = False


class DispatchQueue:
    """Event (1 Event = 1 item, FIFO, drop無し) と State通知 (種別ごとに
    pending 最大1件) を enqueue 順の FIFO で merge する Queue。

    State型とEvent型の間に明示的な優先順位は設けない (#17)。
    """

    def __init__(self) -> None:
        self._queue = EventQueue()

    def new_state_channel(self, notification_type: str) -> StateChannel:
        return StateChannel(notification_type, self)

    def push_event(self, event: RuntimeEvent) -> None:
        """Button / AI Result 等、drop してはいけない Event を投入する。"""
        self._push(event)

    def _push(self, event: RuntimeEvent) -> None:
        self._queue.push(event)

    def pop(self) -> RuntimeEvent:
        event = self._queue.pop(block=True)
        if isinstance(event.payload, StateChannel):
            event.payload._clear_pending()
        return event


class DispatchingVisionSource:
    """既存の Vision Input Source (DetectionEvent を生成する Iterable) を
    background thread で読み、Dispatch Queue 経由で同期 Runtime Core へ渡す。

    `RobotRuntime` から見た `InputSource` の契約
    (`__iter__(self) -> Iterator[DetectionEvent]`) は変えないため、
    `RobotRuntime` / Reasoner / ActionPlanner / Executor / Logger 側の
    実装・テストは一切変更不要。

    Producer thread は daemon thread とする。stdin のブロッキング読み取りは
    Python から安全に割り込めないため、Shutdown 時は明示的な停止を試みず、
    プロセス終了時に OS へ回収させる (stdin 読み取り以外の外部リソースを
    保持しないため、この方式で AGENTS.md の Shutdown 方針と矛盾しない)。
    SIGINT は引き続き main thread のみで処理され (Python の signal handler は
    main thread でのみ実行される)、`DispatchQueue.pop()` のブロッキングは
    既存の stdin 直接読み取りと同様に signal で割り込み可能である。
    """

    def __init__(
        self,
        source: Iterable[DetectionEvent],
        dispatch: DispatchQueue | None = None,
    ) -> None:
        self._source = source
        self._dispatch = dispatch or DispatchQueue()
        self._channel: StateChannel[DetectionEvent] = self._dispatch.new_state_channel(
            "VISION_STATE_UPDATED"
        )
        self._thread = threading.Thread(target=self._produce, daemon=True)
        self._started = False

    def __iter__(self) -> Iterator[DetectionEvent]:
        if not self._started:
            self._started = True
            self._thread.start()
        return self

    def __next__(self) -> DetectionEvent:
        event = self._dispatch.pop()
        if event.type == self._channel.notification_type:
            value = self._channel.latest()
            assert value is not None  # 通知が来た時点で必ず1件は publish 済み
            return value
        if event.type == _EOF:
            raise StopIteration
        if event.type == _ERROR:
            raise event.payload
        # Milestone 1 時点ではこの Source は Vision 専用であり、他の Event 種別を
        # 消費する経路がない。静かに無視せず、想定外として扱う。
        raise RuntimeError(f"Unhandled dispatch event type: {event.type!r}")

    def _produce(self) -> None:
        try:
            for detection_event in self._source:
                self._channel.publish(detection_event)
        except Exception as exc:  # noqa: BLE001 - main thread 側へ伝播させる
            self._dispatch.push_event(RuntimeEvent(_ERROR, payload=exc))
            return
        self._dispatch.push_event(RuntimeEvent(_EOF))
