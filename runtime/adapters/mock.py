"""Whisplay 実機なしで Runtime の Action / Event 経路を確認するための
Fake Adapter / Fake Button (Milestone 2)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ..dispatch import DispatchQueue
from ..event import RuntimeEvent
from . import DeviceUnavailableError

BUTTON_PRESSED = "BUTTON_PRESSED"


@dataclass
class FakeHardwareAdapter:
    """呼び出しを記録するだけの Adapter。

    `fail_on` にメソッド名を入れておくと、そのメソッド呼び出し時に
    `DeviceUnavailableError` を送出し、非必須 I/O 障害を再現できる。
    """

    fail_on: frozenset[str] = field(default_factory=frozenset)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def display(self, message: str) -> None:
        self._call("display", message)

    def set_led(self, state: str) -> None:
        self._call("set_led", state)

    def play_audio(self, clip: str) -> None:
        self._call("play_audio", clip)

    def _call(self, method: str, value: str) -> None:
        if method in self.fail_on:
            raise DeviceUnavailableError(f"{method} unavailable")
        self.calls.append((method, value))


class FakeButtonSource:
    """Button 押下を模擬し、Dispatch Queue へ BUTTON_PRESSED Event を投入する。

    実機 Button Adapter (Milestone 5/6) が用意されるまでの代替。
    """

    def __init__(self, dispatch: DispatchQueue) -> None:
        self._dispatch = dispatch

    def press(self) -> None:
        self._dispatch.push_event(RuntimeEvent(BUTTON_PRESSED))
