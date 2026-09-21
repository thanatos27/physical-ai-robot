"""Robot Runtime の共通データモデル。

他の Runtime モジュールには依存しない。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

SCHEMA_VERSION = "0.1"


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


@dataclass(frozen=True)
class Decision:
    type: DecisionType


class ActionType(str, Enum):
    REPORT_PERSON_DETECTED = "REPORT_PERSON_DETECTED"
    REPORT_NO_PERSON = "REPORT_NO_PERSON"


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
class RobotLoopRecord:
    """1回の Runtime Loop の記録。1行の JSONL として保存される。"""

    schema_version: str
    loop_id: int
    timestamp: int
    observation: Observation
    decision: Decision
    action: Action
    result: ActionResult

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
