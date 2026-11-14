"""push 하지 않은 코드를 Colab 에서 시험할 때 쓰는 압축 파일을 만든다: python tools/pack_source.py

git 에 올라갈 파일만 담는다 (추적 중인 파일 + 아직 add 하지 않았지만 .gitignore 에 걸리지 않는 파일).
secrets.env, data/, results/, .venv/ 는 .gitignore 에 있으므로 들어가지 않는다.
만든 파일을 Colab 의 /content 나 Google Drive 에 올리고 main.ipynb 첫 셀에서 USE_ARCHIVE = True 로 실행한다.
"""
from __future__ import annotations

import argparse
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "ts2img_src.tar.gz"   # .gitignore 에 있다


def source_files() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                       cwd=ROOT, capture_output=True, check=True)
    files = [f for f in r.stdout.decode("utf-8").split("\0") if f]
    return sorted(f for f in files if (ROOT / f).is_file())   # 지웠지만 아직 commit 하지 않은 파일은 뺀다


def pack(out: Path = DEFAULT_OUT) -> tuple[Path, int]:
    out = out.resolve()
    files = [f for f in source_files() if (ROOT / f).resolve() != out]
    with tarfile.open(out, "w:gz") as tar:
        for f in files:
            tar.add(ROOT / f, arcname=f)
    return out, len(files)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="push 하지 않은 코드를 Colab 으로 옮길 압축 파일을 만든다")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"저장할 위치 (기본: {DEFAULT_OUT.name})")
    args = ap.parse_args()
    path, n = pack(args.out)
    print(f"wrote {path} (파일 {n}개, {path.stat().st_size / 1024:.0f} KB)")
    print("다음: 이 파일을 Colab 의 /content 또는 Google Drive '내 드라이브' 에 올리고, main.ipynb 첫 셀에서 USE_ARCHIVE = True 로 실행")
