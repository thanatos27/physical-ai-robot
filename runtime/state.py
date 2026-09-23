"""State型入力 (Vision 等) の「最新値のみ保持」ボックスと、Runtime の世界状態。

State型は最新値のみが重要であり、古い値を無制限に Queue へ蓄積しない (Latest wins)。

詳細は docs/specs/phase-0.8-stationary-ai-robot.md #10.1, #11。

Note: 設計仕様 #11 では概念モデル名を "RuntimeState" としているが、
`runtime.robot_runtime.RuntimeState` (Runtime lifecycle enum: STARTING/RUNNING/...)
と名前が衝突するため、ここでは `RuntimeWorldState` という名前を用いる。
"""

from __future__ import annotations

import threading
from typing import Generic, Optional, TypeVar

from .models import Observation

T = TypeVar("T")


class LatestValueBox(Generic[T]):
    """最新値だけを保持するスレッドセーフなボックス (Latest wins)。

    古い値は上書きされて破棄されるため、Queue のように無制限に蓄積することはない。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: Optional[T] = None
        self._has_value = False

    def set(self, value: T) -> None:
        with self._lock:
            self._value = value
            self._has_value = True

    def get(self) -> Optional[T]:
        with self._lock:
            return self._value if self._has_value else None


class RuntimeWorldState:
    """Runtime Core が保持する最小限の世界状態。

    Phase 0.8 Milestone 1 時点では Vision のみ扱う。devices / ai 等の状態は
    それらを必要とする Milestone (Hardware Abstraction / AI Job) で追加する。
    """

    def __init__(self) -> None:
        self._vision = LatestValueBox[Observation]()

    def update_vision(self, observation: Observation) -> None:
        self._vision.set(observation)

    @property
    def latest_vision(self) -> Optional[Observation]:
        return self._vision.get()
