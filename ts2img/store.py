"""run 폴더 입출력. predictions.jsonl 은 문항이 끝날 때마다 한 줄씩 덧붙인다."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# 다시 시도하지 않는 상태. error 는 다음 실행에서 다시 시도한다
FINAL_STATUS = {"ok", "context_overflow"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json(path: Path, obj) -> None:
    """임시 파일에 쓴 뒤 바꿔치기한다. 도중에 죽어도 깨진 파일이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: 다른 프로세스가 읽는 중
            time.sleep(0.1 * (attempt + 1))
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


class RunStore:
    def __init__(self, run_dir: Path):
        self.dir = run_dir
        self.path = run_dir / "predictions.jsonl"
        self._lock = threading.Lock()
        self._fh = None

    def load(self) -> dict[str, dict]:
        """문항 id -> 가장 최근 기록. 깨진 줄(쓰다가 죽은 경우)은 건너뛴다."""
        records: dict[str, dict] = {}
        if not self.path.is_file():
            return records
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "id" in rec:
                    records[rec["id"]] = rec
        return records

    def done_ids(self) -> set[str]:
        return {i for i, r in self.load().items() if r.get("status") in FINAL_STATUS}

    def _open(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        needs_newline = False
        if self.path.is_file() and self.path.stat().st_size > 0:
            with open(self.path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                needs_newline = f.read(1) != b"\n"
        self._fh = open(self.path, "a", encoding="utf-8")
        if needs_newline:
            self._fh.write("\n")

    def append(self, record: dict) -> None:
        with self._lock:
            if self._fh is None:
                self._open()
            self._fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
