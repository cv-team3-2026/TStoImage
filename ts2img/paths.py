"""경로 모음. 환경변수로 data / results 위치를 바꿀 수 있다."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "configs"
EXPERIMENTS = CONFIGS / "experiments"


def data_dir() -> Path:
    return Path(os.environ.get("TS2IMG_DATA_DIR") or ROOT / "data")


def results_dir() -> Path:
    return Path(os.environ.get("TS2IMG_RESULTS_DIR") or ROOT / "results")


def runs_dir() -> Path:
    return results_dir() / "runs"


def reports_dir() -> Path:
    return results_dir() / "reports"


def experiment_dir(name: str) -> Path:
    """실험 단위 상태 파일(status.json, run.log, pid) 위치."""
    return results_dir() / "experiments" / name


def serve_dir() -> Path:
    return results_dir() / "serve"


def find_experiment(arg: str) -> Path:
    """yaml 경로 또는 configs/experiments 안의 이름을 받아 실제 경로를 돌려준다."""
    p = Path(arg)
    candidates = [p, EXPERIMENTS / arg, EXPERIMENTS / f"{arg}.yaml", EXPERIMENTS / f"{arg}.yml"]
    for c in candidates:
        if c.is_file():
            return c
    names = ", ".join(sorted(x.stem for x in EXPERIMENTS.glob("*.y*ml")))
    raise FileNotFoundError(f"실험 설정을 찾을 수 없습니다: {arg} (사용 가능: {names})")
