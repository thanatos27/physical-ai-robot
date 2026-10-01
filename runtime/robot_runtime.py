"""Robot Runtime 本体 (Orchestrator)。

Input → Observation → Reason → Action → Execute → Log を同期・逐次に回す。
個別の判断・変換ロジックは持たず、各コンポーネントを順に呼び出すだけとする。

使い方 (リポジトリルートから):
    rpicam-hello ... | python3 -m runtime.robot_runtime
    python -m runtime.robot_runtime < detections.jsonl
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterator, Sequence

from .action import (
    ActionPlanner,
    AIRequestExecutor,
    ConsoleExecutor,
    Executor,
    HardwareExecutor,
)
from .adapters import DeviceUnavailableError, HardwareAdapter
from .ai import AIJobManager, SubprocessAIBackend
from .dispatch import DispatchingVisionSource, DispatchQueue
from .event import RuntimeEvent
from .input import InputSource, stdin_input_source
from .models import (
    SCHEMA_VERSION,
    DetectionEvent,
    EventRecord,
    Observation,
    RobotLoopRecord,
)
from .observation import ObservationAdapter
from .reasoner import Reasoner, RuleBasedReasoner
from .robot_logger import JsonlRobotDataLogger, RobotDataLogger

logger = logging.getLogger(__name__)


class RuntimeState(Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class RobotRuntime:
    def __init__(
        self,
        input_source: InputSource,
        adapter: ObservationAdapter,
        reasoner: Reasoner,
        planner: ActionPlanner,
        executor: Executor,
        data_logger: RobotDataLogger,
    ) -> None:
        self._input_source = input_source
        self._adapter = adapter
        self._reasoner = reasoner
        self._planner = planner
        self._executor = executor
        self._data_logger = data_logger

        self.state = RuntimeState.STARTING
        self._cycle_id = 0
        self._stop_requested = False
        self._waiting_for_input = False

    @property
    def waiting_for_input(self) -> bool:
        """入力待ち中か。SIGINT でループを中断してよいかの判定に使う。"""
        return self._waiting_for_input

    def request_stop(self) -> None:
        """現在処理中のイベントを完了した後にループを終了させる。"""
        self._stop_requested = True

    def run(self) -> int:
        """EOF・stop 要求・SIGINT まで実行し、処理した Loop 数を返す。

        想定外の例外は握りつぶさず伝播させる。Logger は必ず close される。
        """
        logger.info("Robot Runtime started")
        self.state = RuntimeState.RUNNING
        try:
            self._loop()
        finally:
            self.state = RuntimeState.STOPPING
            try:
                self._data_logger.close()
            finally:
                self.state = RuntimeState.STOPPED
                logger.info("Robot Runtime stopped")
        return self._cycle_id

    def _loop(self) -> None:
        events = iter(self._input_source)
        while not self._stop_requested:
            # KeyboardInterrupt を受け付けるのは入力待ちの間だけにする。
            # レコード書き込みの途中で中断されて JSONL の行が壊れるのを避ける。
            self._waiting_for_input = True
            try:
                event = next(events)
            except StopIteration:
                break
            except KeyboardInterrupt:
                logger.info("Interrupted; stopping")
                break
            finally:
                self._waiting_for_input = False
            self._process(event)

    def _process(self, event: DetectionEvent | RuntimeEvent) -> None:
        observation: Observation | None
        event_record: EventRecord | None
        if isinstance(event, DetectionEvent):
            observation = self._adapter.adapt(event)
            event_record = None
            reasoner_input = observation
            timestamp = observation.timestamp
        else:
            # Event型入力 (Button等) には Vision のような capture 時刻が無いため、
            # Runtime がこの cycle を処理した時刻を timestamp とする
            # (Vision の timestamp は検出時刻、Event の timestamp は処理時刻で
            # 意味が異なる点に注意)。
            observation = None
            event_record = EventRecord(type=event.type, payload=event.payload)
            reasoner_input = event
            timestamp = int(time.time() * 1000)

        decision = self._reasoner.reason(reasoner_input)
        action = self._planner.plan(decision)
        result = self._executor.execute(action)

        self._cycle_id += 1
        self._data_logger.log(
            RobotLoopRecord(
                schema_version=SCHEMA_VERSION,
                cycle_id=self._cycle_id,
                timestamp=timestamp,
                observation=observation,
                event=event_record,
                decision=decision,
                action=action,
                result=result,
            )
        )


@contextlib.contextmanager
def _stop_on_sigint(runtime: RobotRuntime) -> Iterator[None]:
    """SIGINT で runtime を止める。処理中なら現在のイベント完了後に止まる。"""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def handler(signum: int, frame: object) -> None:
        runtime.request_stop()
        if runtime.waiting_for_input:
            raise KeyboardInterrupt

    previous = signal.signal(signal.SIGINT, handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def _default_log_path() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"logs/robot-data-{stamp}.jsonl"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m runtime.robot_runtime",
        description="stdin から Detection JSONL を読み、Robot Runtime Loop を実行する。",
    )
    parser.add_argument(
        "--log-path",
        default=None,
        help="Robot Data Log (JSONL) の保存先。既定: logs/robot-data-<UTC日時>.jsonl",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Application Log のレベル (stderr へ出力)。既定: INFO",
    )
    parser.add_argument(
        "--hardware",
        default="auto",
        choices=["auto", "none"],
        help=(
            "auto: Whisplay HAT を使う (利用できなければ console 出力のみで継続)。"
            "none: Whisplay を使わない (Phase 0.5 と同じ console 出力のみ)。既定: auto"
        ),
    )
    parser.add_argument(
        "--ai",
        default="none",
        choices=["none", "vlm"],
        help=(
            "vlm: Button press で Hailo VLM Job を起動する (Milestone 7 暫定構成。"
            "カメラを使うため連続 Vision とは同時に使わない)。"
            "none: AI Job を使わない。既定: none"
        ),
    )
    return parser.parse_args(argv)


# per-job subprocess は Job ごとにモデルをロードする (Qwen2-VL 実測 9.9 秒、
# 撮影 / 推論を含め1 Job 十数秒)。初回の HEF 読み込みが遅い場合も考慮した値。
VLM_JOB_TIMEOUT_SEC = 60.0
VLM_BACKEND_NAME = "hailo-vlm-subprocess"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_VLM_WORKER = _REPO_ROOT / "edge" / "vlm_worker" / "vlm_worker.py"
_DEFAULT_GENAI_PYTHON = "~/venvs/hailo-apps/bin/python"
_DEFAULT_VLM_HEF = "/usr/local/hailo/resources/models/hailo10h/Qwen2-VL-2B-Instruct.hef"


def _open_vlm(dispatch: DispatchQueue) -> AIJobManager | None:
    """VLM Job 用の AIJobManager を作る。前提が揃わなければ None (AI fallback, NFR-05)。"""
    python = Path(os.path.expanduser(os.environ.get("HAILO_GENAI_PYTHON", _DEFAULT_GENAI_PYTHON)))
    hef = Path(os.environ.get("VLM_HEF_PATH", _DEFAULT_VLM_HEF))
    missing = [str(p) for p in (python, _VLM_WORKER, hef) if not p.exists()]
    if missing:
        logger.warning("VLM unavailable; continuing without AI Jobs (missing: %s)", ", ".join(missing))
        return None
    backend = SubprocessAIBackend([str(python), str(_VLM_WORKER), "--hef", str(hef)])
    logger.info("VLM AI Job backend active (per-job subprocess)")
    return AIJobManager(backend, dispatch.push_event)


def _open_whisplay(dispatch: DispatchQueue) -> HardwareAdapter | None:
    """Whisplay を取得する。取得できなければ None (縮退運転, AC-24)。"""
    from .adapters.whisplay import RealWhisplayAdapter

    try:
        adapter = RealWhisplayAdapter(dispatch)
    except DeviceUnavailableError as exc:
        logger.warning("Whisplay unavailable; continuing with console output only: %s", exc)
        return None
    logger.info("Whisplay hardware adapter active")
    return adapter


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    # Application Log は stderr。stdout は ConsoleExecutor の出力に使う。
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
        force=True,
    )

    hardware: HardwareAdapter | None = None
    ai_manager: AIJobManager | None = None
    try:
        # Phase 0.8 Dispatch path (docs/specs/phase-0.8-implementation-plan.md
        # #Regression Boundary): Vision は State Coalescing を経由する。
        # raw DetectionEvent 数と RobotLoopRecord 数の一致は要求しない。
        vision_source = DispatchingVisionSource(stdin_input_source())
        # Button press と AI Result は Vision と同じ Dispatch Queue へ投入される。
        if args.hardware == "auto":
            hardware = _open_whisplay(vision_source.dispatch_queue)
        if args.ai == "vlm":
            ai_manager = _open_vlm(vision_source.dispatch_queue)

        executor: Executor = (
            HardwareExecutor(hardware) if hardware is not None else ConsoleExecutor()
        )
        if ai_manager is not None:
            executor = AIRequestExecutor(
                executor, ai_manager, VLM_JOB_TIMEOUT_SEC, VLM_BACKEND_NAME
            )
        runtime = RobotRuntime(
            input_source=vision_source,
            adapter=ObservationAdapter(),
            reasoner=RuleBasedReasoner(vlm_enabled=ai_manager is not None),
            planner=ActionPlanner(),
            executor=executor,
            data_logger=JsonlRobotDataLogger(args.log_path or _default_log_path()),
        )
        with _stop_on_sigint(runtime):
            runtime.run()
    except Exception:
        logger.exception("Robot Runtime failed")
        return 1
    finally:
        try:
            # 実行中の VLM worker を終了・回収してから Whisplay を解放する (#15.3)。
            if ai_manager is not None:
                ai_manager.shutdown()
        finally:
            if hardware is not None:
                hardware.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
