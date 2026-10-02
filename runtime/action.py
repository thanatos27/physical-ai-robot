"""Decision → Action の計画と、Action の実行。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol, TextIO

from .adapters import DeviceUnavailableError, HardwareAdapter
from .ai import AIJob, AIJobManager, AIJobType, new_job_id
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
    # Button の既存表示を VLM Job の受付フィードバックとして使う (#11.4)。
    DecisionType.VLM_REQUESTED: Action(ActionType.REQUEST_VLM, "Button pressed"),
    # Milestone 4: AI Result Event が Core まで届くことの最小限の proof。
    # 実際の AI 出力内容を表示する対応は Milestone 7 (AI Connectivity Proof)
    # で ActionPlanner に Decision の payload を持たせる際に拡張する。
    DecisionType.AI_RESULT_RECEIVED: Action(
        ActionType.DISPLAY_MESSAGE, "AI result received"
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
# Vision E2E (Milestone 6, AC-18) で Display / LED へもミラーする LED 状態。
_REPORT_LED_STATE: dict[ActionType, str] = {
    ActionType.REPORT_PERSON_DETECTED: "GREEN",
    ActionType.REPORT_NO_PERSON: "OFF",
}
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

    # 直前と同じ内容なら再出力しない出力先。LCD 描画は1回ごとのコストが大きく、
    # Vision (約30fps) の毎 cycle で描画すると Core の応答性 (AC-27) を損なうため。
    _DEDUPED_METHODS = frozenset({"display", "set_led"})

    def __init__(self, adapter: HardwareAdapter, stream: TextIO | None = None) -> None:
        self._adapter = adapter
        self._stream = stream
        self._lock = threading.Lock()
        self._device_status: dict[str, DeviceStatus] = {}
        self._last_output: dict[str, str] = {}

    def device_status(self) -> dict[str, DeviceStatus]:
        with self._lock:
            return dict(self._device_status)

    def execute(self, action: Action) -> ActionResult:
        if action.type in _REPORT_ACTIONS:
            print(action.message, file=self._stream, flush=True)
            self._mirror_report(action)
            return ActionResult(ActionStatus.SUCCESS)

        method_name = _HARDWARE_ACTIONS.get(action.type)
        if method_name is None:
            return ActionResult(
                ActionStatus.FAILED, f"unsupported action: {action.type!r}"
            )

        error = self._call_adapter(method_name, action.message)
        if error is not None:
            return ActionResult(ActionStatus.FAILED, error)
        return ActionResult(ActionStatus.SUCCESS)

    def _mirror_report(self, action: Action) -> None:
        # Phase 0.5 から実機確認済みの console report を主とし、Display / LED への
        # 出力は best-effort のミラーとする。ミラー失敗は report の結果
        # (SUCCESS) に影響させない (Preserve Verified Configurations, AC-24)。
        self._call_adapter("display", action.message)
        led_state = _REPORT_LED_STATE.get(action.type)
        if led_state is not None:
            self._call_adapter("set_led", led_state)

    def _call_adapter(self, method_name: str, value: str) -> str | None:
        """成功なら None、失敗ならエラー詳細を返す。"""
        deduped = method_name in self._DEDUPED_METHODS
        if deduped and self._last_output.get(method_name) == value:
            return None
        try:
            getattr(self._adapter, method_name)(value)
        except DeviceUnavailableError as exc:
            logger.warning("Hardware action failed: %s (%s)", method_name, exc)
            self._set_device_status(method_name, DeviceStatus(False, str(exc)))
            self._last_output.pop(method_name, None)
            return str(exc)
        self._set_device_status(method_name, DeviceStatus(True))
        if deduped:
            self._last_output[method_name] = value
        return None

    def _set_device_status(self, device: str, status: DeviceStatus) -> None:
        with self._lock:
            self._device_status[device] = status


class AIRequestExecutor:
    """`REQUEST_VLM` を VLM Job として AIJobManager へ投入する (Milestone 7)。

    それ以外の Action は delegate (HardwareExecutor / ConsoleExecutor) へ渡す。
    Job の完了は待たず、結果は後続の AI_RESULT Event として Runtime へ戻る。
    投入した job_id を ActionResult.detail に残し、要求した cycle と AI Result の
    cycle を Robot Event Log 上で対応付けられるようにする (AC-21)。
    """

    def __init__(
        self,
        delegate: Executor,
        manager: AIJobManager,
        job_timeout: float,
        backend_name: str,
    ) -> None:
        self._delegate = delegate
        self._manager = manager
        self._job_timeout = job_timeout
        self._backend_name = backend_name

    def execute(self, action: Action) -> ActionResult:
        if action.type != ActionType.REQUEST_VLM:
            return self._delegate.execute(action)

        job = AIJob(
            job_id=new_job_id(),
            type=AIJobType.VLM,
            backend=self._backend_name,
            input=None,
            timeout=self._job_timeout,
        )
        self._manager.submit(job)
        # 受付フィードバック。表示の成否は Job 投入の結果に影響させない。
        self._delegate.execute(Action(ActionType.DISPLAY_MESSAGE, action.message))
        return ActionResult(ActionStatus.SUCCESS, f"job_id={job.job_id}")
