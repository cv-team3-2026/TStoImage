"""변화량이 큰 지점. chart 파일이 아니라 공용 계산이다."""
from __future__ import annotations

import numpy as np


def _diffs(values) -> np.ndarray:
    a = np.asarray(values, dtype=float)
    if len(a) < 2:
        return np.asarray([], dtype=float)
    d = np.abs(np.diff(a))
    d[~np.isfinite(d)] = np.nan
    return d


def strongest(values) -> int | None:
    """가장 큰 |diff| 의 오른쪽 index. 없으면 None."""
    d = _diffs(values)
    if len(d) == 0 or not np.isfinite(d).any():
        return None
    return int(np.nanargmax(d)) + 1


def points(values, z: float = 2.5, limit: int = 12) -> list[int]:
    """중앙값 + z * MAD 를 넘는 변화의 오른쪽 index. 큰 것부터 최대 limit 개, index 순."""
    d = _diffs(values)
    finite = d[np.isfinite(d)]
    if len(finite) == 0:
        return []
    med = float(np.median(finite))
    mad = float(np.median(np.abs(finite - med)))
    scale = mad if mad > 0 else float(np.std(finite) or 0)
    thr = med + z * scale
    idx = [i + 1 for i, v in enumerate(d) if np.isfinite(v) and v >= thr and v > 0]
    if len(idx) > limit:
        idx = sorted(idx, key=lambda i: d[i - 1], reverse=True)[:limit]
    return sorted(idx)


def window(sample, half: int) -> tuple[int, int]:
    """sample 전체에서 가장 큰 변화 주변 [lo, hi)."""
    best_i, best_d, best_n = 0, -1.0, 1
    for series in sample.series:
        d = _diffs(series.values)
        if len(d) == 0 or not np.isfinite(d).any():
            continue
        j = int(np.nanargmax(d))
        if float(d[j]) > best_d:
            best_d = float(d[j])
            best_i = j + 1
            best_n = len(series.values)
    lo = max(0, best_i - int(half))
    hi = min(best_n, best_i + int(half) + 1)
    if hi - lo < 2:
        lo, hi = 0, best_n
    return lo, hi
