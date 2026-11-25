#!/usr/bin/env python3
"""따릉이 applied 실험용 Seoul Bike CSV 를 자동으로 받는다.

UCI zip 을 받아 data/applied/seoul_bike/ 에 푼다. 이미 있으면 건너뛴다.
applied_seoul / applied_seoul_peak / lab 실험이 같은 파일을 쓴다.

사용:
  python tools/download_applied_seoul.py
  # 또는 레포 루트에서
  python -m ts2img download applied_seoul applied_seoul_peak
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from ts2img.benchmarks import get_benchmark
    from ts2img import ui

    for name in ("applied_seoul", "applied_seoul_peak"):
        b = get_benchmark(name)
        b.ensure_data()
        path = b.csv_path()
        ui.ok(f"{name}: {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
