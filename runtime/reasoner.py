"""Observation → Decision。ハードウェアの事情は知らない。"""

from __future__ import annotations

from typing import Protocol

from .models import Decision, DecisionType, Observation

PERSON = "person"


class Reasoner(Protocol):
    def reason(self, observation: Observation) -> Decision: ...


class RuleBasedReasoner:
    """person が1件でも存在すれば PERSON_DETECTED、なければ NO_PERSON。"""

    def reason(self, observation: Observation) -> Decision:
        if any(obj.type == PERSON for obj in observation.objects):
            return Decision(DecisionType.PERSON_DETECTED)
        return Decision(DecisionType.NO_PERSON)
