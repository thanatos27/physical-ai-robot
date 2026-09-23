"""Robot Runtime の共通データモデル。

他の Runtime モジュールには依存しない。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

SCHEMA_VERSION = "0.2"


# --- 外部入力: detection_logger の JSONL 1行に対応 -----------------------------


@dataclass(frozen=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Detection:
    # JSON上のキーは "class" だが Python の予約語のため class_name とする
    class_name: str
    category: int
    confidence: float
    bbox: BoundingBox


@dataclass(frozen=True)
class DetectionEvent:
    timestamp: int
    detections: tuple[Detection, ...]


# --- Runtime 内部の世界表現 ---------------------------------------------------


@dataclass(frozen=True)
class ObservedObject:
    type: str
    confidence: float
    bounding_box: BoundingBox


@dataclass(frozen=True)
class Observation:
    timestamp: int
    objects: tuple[ObservedObject, ...]


# --- Reason / Action ---------------------------------------------------------


class DecisionType(str, Enum):
    PERSON_DETECTED = "PERSON_DETECTED"
    NO_PERSON = "NO_PERSON"
    BUTTON_ACKNOWLEDGED = "BUTTON_ACKNOWLEDGED"
    AI_RESULT_RECEIVED = "AI_RESULT_RECEIVED"


@dataclass(frozen=True)
class Decision:
    type: DecisionType


class ActionType(str, Enum):
    REPORT_PERSON_DETECTED = "REPORT_PERSON_DETECTED"
    REPORT_NO_PERSON = "REPORT_NO_PERSON"
    # Whisplay Hardware Action (#13, Milestone 2)。LED状態や再生する音声clipの
    # 識別子も、既存 schema を変えないため message (str) に格納する。
    DISPLAY_MESSAGE = "DISPLAY_MESSAGE"
    SET_LED = "SET_LED"
    PLAY_AUDIO = "PLAY_AUDIO"


@dataclass(frozen=True)
class Action:
    type: ActionType
    message: str


class ActionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ActionResult:
    status: ActionStatus
    detail: str | None = None


# --- Robot Data Log ----------------------------------------------------------


@dataclass(frozen=True)
class EventRecord:
    """Robot Event Log 用の Event 型入力 (Button 等) の記録。

    `runtime.event.RuntimeEvent` と構造は同じだが、models.py は他の runtime
    モジュールに依存しない方針のため、ここで独立して定義する。
    """

    type: str
    payload: Any = None


@dataclass(frozen=True)
class RobotLoopRecord:
    """1 cycle (Observation または Event → Reason → Action → Result) の記録。

    1行の JSONL として保存される。

    schema v0.2 (#18.2, Milestone 3 Structured Event Log / Traceability):
    - `loop_id` を `cycle_id` へ改名した (意味は同じ: 1から始まる連番の
      correlation identifier)。
    - `observation` は Vision 由来の cycle でのみ値を持つ (Optional)。
    - `event` を新設し、Button 等 Event 型入力由来の cycle でのみ値を持つ。
      `observation` / `event` はどちらか一方だけが非 None になる。
    - v0.1 との後方互換性は取らない (既知の外部 log reader は存在しない)。
    """

    schema_version: str
    cycle_id: int
    timestamp: int
    observation: Observation | None
    event: EventRecord | None
    decision: Decision
    action: Action
    result: ActionResult

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
