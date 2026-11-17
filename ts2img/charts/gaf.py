"""Gramian Angular Summation Field. series 마다 한 장에 쌓는다.

값이 길면 max_points 개로 줄인다. 그림 한 변이 포인트 수와 같기 때문이다.
yaml 예: {use: gaf, max_points: 128}
"""
import matplotlib.pyplot as plt
import numpy as np

from ts2img.charts._format import normalize, resample, series_of
from ts2img.charts.base import fig_to_image

VERSION = 1


def gasf(values: np.ndarray) -> np.ndarray:
    scaled = np.clip(normalize(values) * 2 - 1, -1, 1)
    phi = np.arccos(scaled)
    return np.cos(phi[:, None] + phi[None, :])


def render(sample, max_points: int = 128, dpi: int = 100, fmt: str = "jpeg"):
    rows = series_of(sample) or [("series_0", np.zeros(2))]
    n = len(rows)
    fig, axes = plt.subplots(n, 1, figsize=(4, 3.2 * n), squeeze=False)
    for ax, (name, values) in zip(axes[:, 0], rows):
        field = gasf(resample(values, max_points))
        im = ax.imshow(field, cmap="coolwarm", vmin=-1, vmax=1, interpolation="nearest")
        ax.set_title(name, fontsize=9)
        ax.set_xlabel("Index")
        ax.set_ylabel("Index")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return [fig_to_image(fig, dpi=dpi, fmt=fmt)]
