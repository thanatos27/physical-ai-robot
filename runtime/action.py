"""Decision → Action の計画と、Action の実行。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol, TextIO

from .adapters import DeviceUnavailableError, HardwareAdapter
from .models import (
    Action,
    ActionResult,
    ActionStatus,
    ActionType,
    Decision,
    DecisionType,
)

logger = logging.getLogger(__name__)

_PLANS: dict[DecisionType, Action] = {
    DecisionType.PERSON_DETECTED: Action(
        ActionType.REPORT_PERSON_DETECTED, "Person detected"
    ),
    DecisionType.NO_PERSON: Action(ActionType.REPORT_NO_PERSON, "No person detected"),
    # Button E2E (#17, Milestone 2 実装計画) の proof として Display Action を返す。
    # SET_LED / PLAY_AUDIO も Executor 側では利用可能だが、Phase 0.8 では
    # Button press に対する具体的な UX は未確定のため、最小限の1 Action とする。
    DecisionType.BUTTON_ACKNOWLEDGED: Action(
        ActionType.DISPLAY_MESSAGE, "Button pressed"
    ),
}

_CONSOLE_ACTIONS = frozenset(ActionType)


class ActionPlanner:
    def plan(self, decision: Decision) -> Action:
        return _PLANS[decision.type]


class Executor(Protocol):
    def execute(self, action: Action) -> ActionResult: ...


class ConsoleExecutor:
    """Action の message をコンソールへ出力する。

    stream が None の場合は呼び出し時点の sys.stdout を使う。
    想定内の失敗は FAILED を返し、想定外の例外は握りつぶさず伝播させる。
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def execute(self, action: Action) -> ActionResult:
        if action.type not in _CONSOLE_ACTIONS:
            return ActionResult(
                ActionStatus.FAILED, f"unsupported action: {action.type!r}"
            )
        print(action.message, file=self._stream, flush=True)
        return ActionResult(ActionStatus.SUCCESS)


_REPORT_ACTIONS = frozenset(
    {ActionType.REPORT_PERSON_DETECTED, ActionType.REPORT_NO_PERSON}
)
_HARDWARE_ACTIONS: dict[ActionType, str] = {
    ActionType.DISPLAY_MESSAGE: "display",
    ActionType.SET_LED: "set_led",
    ActionType.PLAY_AUDIO: "play_audio",
}


@dataclass(frozen=True)
class DeviceStatus:
    available: bool
    detail: str | None = None


class HardwareExecutor:
    """Vision の Console Report と Whisplay Hardware Action の両方を実行する。

    Whisplay 固有 API は `HardwareAdapter` の背後に隠され、ここでも直接は
    参照しない。非必須 I/O (`DeviceUnavailableError`) は Runtime 全体を
    止めず FAILED を返し、Application Log へ記録する (NFR-04, AC-23〜25)。
    """

    def __init__(self, adapter: HardwareAdapter, stream: TextIO | None = None) -> None:
        self._adapter = adapter
        self._stream = stream
        self._lock = threading.Lock()
        self._device_status: dict[str, DeviceStatus] = {}

    def device_status(self) -> dict[str, DeviceStatus]:
        with self._lock:
            return dict(self._device_status)

    def execute(self, action: Action) -> ActionResult:
        if action.type in _REPORT_ACTIONS:
            print(action.message, file=self._stream, flush=True)
            return ActionResult(ActionStatus.SUCCESS)

        method_name = _HARDWARE_ACTIONS.get(action.type)
        if method_name is None:
            return ActionResult(
                ActionStatus.FAILED, f"unsupported action: {action.type!r}"
            )

        try:
            getattr(self._adapter, method_name)(action.message)
        except DeviceUnavailableError as exc:
            logger.warning("Hardware action failed: %s (%s)", method_name, exc)
            self._set_device_status(method_name, DeviceStatus(False, str(exc)))
            return ActionResult(ActionStatus.FAILED, str(exc))

        self._set_device_status(method_name, DeviceStatus(True))
        return ActionResult(ActionStatus.SUCCESS)

    def _set_device_status(self, device: str, status: DeviceStatus) -> None:
        with self._lock:
            self._device_status[device] = status
