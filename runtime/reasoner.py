"""Observation / Event → Decision。ハードウェアの事情は知らない。

設計仕様 #12 Reason Architecture の通り、Rule Reasoner は Vision の
Observation (State) と Button 等の RuntimeEvent (Event) の両方を入力として
受け取る。どちらの場合も Hailo / GPIO / Whisplay driver を直接参照しない。
"""

from __future__ import annotations

from typing import Protocol, Union

from .event import RuntimeEvent
from .models import Decision, DecisionType, Observation

PERSON = "person"
BUTTON_PRESSED = "BUTTON_PRESSED"
AI_RESULT = "AI_RESULT"

ReasonerInput = Union[Observation, RuntimeEvent]


class Reasoner(Protocol):
    def reason(self, input: ReasonerInput) -> Decision: ...


class RuleBasedReasoner:
    """person が1件でも存在すれば PERSON_DETECTED、なければ NO_PERSON。

    Button press event は BUTTON_ACKNOWLEDGED とする。
    """

    def reason(self, input: ReasonerInput) -> Decision:
        if isinstance(input, Observation):
            if any(obj.type == PERSON for obj in input.objects):
                return Decision(DecisionType.PERSON_DETECTED)
            return Decision(DecisionType.NO_PERSON)
        if isinstance(input, RuntimeEvent) and input.type == BUTTON_PRESSED:
            return Decision(DecisionType.BUTTON_ACKNOWLEDGED)
        if isinstance(input, RuntimeEvent) and input.type == AI_RESULT:
            # Milestone 4 時点では AI Result の内容 (成功/失敗/timeout) を
            # 区別した Decision は作らず、Event を受け取り Core へ返せることの
            # 最小限の proof とする (AC-AI-04)。内容に応じた分岐は AI Result の
            # 実利用が始まる Milestone 7 以降で必要に応じて拡張する。
            return Decision(DecisionType.AI_RESULT_RECEIVED)
        raise ValueError(f"Unhandled reasoner input: {input!r}")
