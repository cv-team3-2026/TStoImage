"""results 폴더를 다른 위치(예: Google Drive)와 맞춘다.

Drive 는 잦은 작은 쓰기에 약하다. 실험은 로컬 디스크에 쓰고, 주기적으로 통째로 복사한다.
"""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

from ts2img.paths import results_dir

_SKIP_DIRS = {"serve"}


def _files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and ".tmp" not in p.name and not (set(p.relative_to(root).parts[:1]) & _SKIP_DIRS):
            yield p


def push(dst: Path, src: Path | None = None) -> int:
    """로컬 results -> dst. 크기나 수정 시각이 다른 파일만 복사한다."""
    src = src or results_dir()
    n = 0
    if not src.is_dir():
        return 0
    for p in _files(src):
        q = dst / p.relative_to(src)
        try:
            ps = p.stat()
            if q.is_file():
                qs = q.stat()
                if qs.st_size == ps.st_size and qs.st_mtime >= ps.st_mtime - 1:
                    continue
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
            n += 1
        except OSError:
            continue  # 다음 주기에 다시 시도
    return n


def restore(src: Path, dst: Path | None = None) -> int:
    """src -> 로컬 results. 로컬에 없거나 로컬 쪽이 더 작은 파일만 가져온다."""
    dst = dst or results_dir()
    n = 0
    if not src.is_dir():
        return 0
    for p in _files(src):
        q = dst / p.relative_to(src)
        if q.is_file() and q.stat().st_size >= p.stat().st_size:
            continue
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, q)
        n += 1
    return n


class PeriodicPush:
    """백그라운드 thread 로 interval 초마다 push 한다."""

    def __init__(self, dst: Path, interval: float = 120):
        self.dst, self.interval = dst, interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self._stop.wait(self.interval):
            push(self.dst)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        push(self.dst)
