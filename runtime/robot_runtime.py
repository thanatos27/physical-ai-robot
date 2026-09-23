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
import signal
import sys
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Iterator, Sequence

from .action import ActionPlanner, ConsoleExecutor, Executor
from .dispatch import DispatchingVisionSource
from .input import InputSource, stdin_input_source
from .models import SCHEMA_VERSION, DetectionEvent, RobotLoopRecord
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
        self._loop_id = 0
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
        return self._loop_id

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

    def _process(self, event: DetectionEvent) -> None:
        observation = self._adapter.adapt(event)
        decision = self._reasoner.reason(observation)
        action = self._planner.plan(decision)
        result = self._executor.execute(action)

        self._loop_id += 1
        self._data_logger.log(
            RobotLoopRecord(
                schema_version=SCHEMA_VERSION,
                loop_id=self._loop_id,
                timestamp=observation.timestamp,
                observation=observation,
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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    # Application Log は stderr。stdout は ConsoleExecutor の出力に使う。
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
        force=True,
    )

    try:
        runtime = RobotRuntime(
            # Phase 0.8 Dispatch path (docs/specs/phase-0.8-implementation-plan.md
            # #Regression Boundary): Vision は State Coalescing を経由する。
            # raw DetectionEvent 数と RobotLoopRecord 数の一致は要求しない。
            input_source=DispatchingVisionSource(stdin_input_source()),
            adapter=ObservationAdapter(),
            reasoner=RuleBasedReasoner(),
            planner=ActionPlanner(),
            executor=ConsoleExecutor(),
            data_logger=JsonlRobotDataLogger(args.log_path or _default_log_path()),
        )
        with _stop_on_sigint(runtime):
            runtime.run()
    except Exception:
        logger.exception("Robot Runtime failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
