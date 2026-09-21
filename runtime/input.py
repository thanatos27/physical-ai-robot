"""外部入力(Detection JSONL)の読み込み。

stdin への直接依存はこのモジュールに限定する (ADR 0003)。
"""

from __future__ import annotations

import json
import logging
import math
import sys
from typing import Any, Iterable, Iterator, Protocol, TextIO

from .models import BoundingBox, Detection, DetectionEvent

logger = logging.getLogger(__name__)

_LOG_LINE_LIMIT = 200


class InvalidInputError(ValueError):
    """外部入力が Detection JSON として不正であることを表す。"""


class InputSource(Protocol):
    def __iter__(self) -> Iterator[DetectionEvent]: ...


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidInputError(message)


def _parse_bbox(data: Any) -> BoundingBox:
    _require(isinstance(data, dict), "bbox must be an object")
    for key in ("x", "y", "width", "height"):
        _require(key in data, f"bbox.{key} is missing")
        _require(_is_number(data[key]), f"bbox.{key} must be a finite number")
    return BoundingBox(
        x=data["x"], y=data["y"], width=data["width"], height=data["height"]
    )


def _parse_detection(data: Any) -> Detection:
    _require(isinstance(data, dict), "detection must be an object")
    _require(isinstance(data.get("class"), str), "detection.class must be a string")
    _require(_is_int(data.get("category")), "detection.category must be an integer")
    _require(
        _is_number(data.get("confidence")),
        "detection.confidence must be a finite number",
    )
    _require("bbox" in data, "detection.bbox is missing")
    return Detection(
        class_name=data["class"],
        category=data["category"],
        confidence=data["confidence"],
        bbox=_parse_bbox(data["bbox"]),
    )


def parse_detection_event(line: str) -> DetectionEvent:
    """JSONL 1行を DetectionEvent へ変換する。不正なら InvalidInputError。"""
    if not line.strip():
        raise InvalidInputError("empty line")
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise InvalidInputError(f"not valid JSON: {exc}") from exc

    _require(isinstance(data, dict), "event must be a JSON object")
    _require(_is_int(data.get("timestamp")), "timestamp must be an integer")
    detections = data.get("detections")
    _require(isinstance(detections, list), "detections must be an array")

    return DetectionEvent(
        timestamp=data["timestamp"],
        detections=tuple(_parse_detection(d) for d in detections),
    )


class JsonlInputSource:
    """行単位の JSONL ストリームから DetectionEvent を取り出す。

    不正な行は WARNING を出してスキップし、Runtime 全体は止めない。
    """

    def __init__(self, lines: Iterable[str] | TextIO) -> None:
        self._lines = lines

    def __iter__(self) -> Iterator[DetectionEvent]:
        for line in self._lines:
            try:
                yield parse_detection_event(line)
            except InvalidInputError as exc:
                logger.warning(
                    "Invalid input skipped: %s (line=%r)",
                    exc,
                    line.rstrip("\r\n")[:_LOG_LINE_LIMIT],
                )


def stdin_input_source() -> JsonlInputSource:
    return JsonlInputSource(sys.stdin)
