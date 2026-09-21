"""Robot Data Log。Python 標準 logging との衝突を避けるため logging.py とはしない。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .models import RobotLoopRecord


class RobotDataLogger(Protocol):
    def log(self, record: RobotLoopRecord) -> None: ...

    def close(self) -> None: ...


class JsonlRobotDataLogger:
    """1 RobotLoopRecord = 1行の JSON Lines として追記保存する。

    保存失敗 (OSError 等) は握りつぶさず伝播させる。
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n": Windows でも改行コードを LF に固定する
        self._file = self._path.open("a", encoding="utf-8", newline="\n")

    def log(self, record: RobotLoopRecord) -> None:
        line = json.dumps(record.to_dict(), separators=(",", ":"), ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()
