"""Event型入力 (Button, AI Result 等) の共通モデルと FIFO キュー。

Event型は「発生事実」を保持する入力であり、State型 (Vision 等、latest wins) と異なり
発生順序 (FIFO) を保持する。

詳細は docs/specs/phase-0.8-stationary-ai-robot.md #10.2, #17。
"""

from __future__ import annotations

import queue
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuntimeEvent:
    """Button press / AI Job completed / Error 等、発生事実を表す汎用 Event。"""

    type: str
    payload: Any = field(default=None)


class EventQueue:
    """Event型入力を発生順 (FIFO) に保持するキュー。

    State型の LatestValueBox (runtime/state.py) と異なり、投入された Event は
    取り出されるまで失われない。
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[RuntimeEvent]" = queue.Queue()

    def push(self, event: RuntimeEvent) -> None:
        self._queue.put(event)

    def pop(self, block: bool = True, timeout: float | None = None) -> RuntimeEvent:
        """先頭の Event を取り出す。空で block=False の場合は queue.Empty を送出する。"""
        return self._queue.get(block=block, timeout=timeout)

    def empty(self) -> bool:
        return self._queue.empty()

    def qsize(self) -> int:
        return self._queue.qsize()
