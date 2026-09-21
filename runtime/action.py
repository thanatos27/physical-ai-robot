"""Decision → Action の計画と、Action の実行。"""

from __future__ import annotations

from typing import Protocol, TextIO

from .models import (
    Action,
    ActionResult,
    ActionStatus,
    ActionType,
    Decision,
    DecisionType,
)

_PLANS: dict[DecisionType, Action] = {
    DecisionType.PERSON_DETECTED: Action(
        ActionType.REPORT_PERSON_DETECTED, "Person detected"
    ),
    DecisionType.NO_PERSON: Action(ActionType.REPORT_NO_PERSON, "No person detected"),
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
