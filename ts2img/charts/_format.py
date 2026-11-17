"""heatmap, GAF, spectrogram 이 같이 쓰는 시계열 정리."""
from __future__ import annotations

import numpy as np


def series_of(sample) -> list[tuple[str, np.ndarray]]:
    out = []
    for i, series in enumerate(sample.series):
        values = np.asarray(series.values, dtype=float)
        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
        name = series.name or f"series_{i}"
        out.append((name, values))
    return out


def resample(values: np.ndarray, limit: int) -> np.ndarray:
    """길면 균등한 인덱스로 limit 개만 남긴다."""
    if len(values) <= limit:
        return values
    idx = np.linspace(0, len(values) - 1, int(limit)).astype(int)
    return values[idx]


def normalize(values: np.ndarray) -> np.ndarray:
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-12:
        return np.zeros_like(values)
    return (values - lo) / (hi - lo)
