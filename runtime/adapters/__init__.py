"""Whisplay 固有 API を隠す Hardware Adapter interface (#13, #20)。

Reasoner / Runtime Core からはこの Protocol しか見えない。実機実装
(`whisplay.py`, Milestone 5/6 以降) と Fake 実装 (`mock.py`) を
同じ interface で差し替えられるようにする。
"""

from __future__ import annotations

from typing import Protocol


class DeviceUnavailableError(Exception):
    """非必須 I/O が利用できないことを表す。Executor はこれを FAILED として
    扱い、Runtime 全体は停止させない (NFR-04, AC-24)。"""


class HardwareAdapter(Protocol):
    def display(self, message: str) -> None: ...

    def set_led(self, state: str) -> None: ...

    def play_audio(self, clip: str) -> None: ...
