"""series 값을 시간 × 채널 색 지도로 그린다.

한 series 는 가로로 긴 색 띠가 된다. 여러 series 는 한 행씩 쌓인다.
yaml 예: heatmap
"""
import matplotlib.pyplot as plt
import numpy as np

from ts2img.charts._format import normalize, series_of
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample, dpi: int = 100, fmt: str = "jpeg"):
    rows = series_of(sample)
    if not rows:
        rows = [("series_0", np.zeros(2))]
    image = np.vstack([normalize(values)[None, :] for _, values in rows])
    fig_h = max(2.0, 0.7 * len(rows) + 1.0)
    fig, ax = plt.subplots(figsize=(6, fig_h))
    im = ax.imshow(image, aspect="auto", cmap="viridis", interpolation="nearest", vmin=0, vmax=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([name for name, _ in rows], fontsize=8)
    ax.set_xlabel("Index")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return [fig_to_image(fig, dpi=dpi, fmt=fmt)]
