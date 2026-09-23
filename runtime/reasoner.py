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
        raise ValueError(f"Unhandled reasoner input: {input!r}")
