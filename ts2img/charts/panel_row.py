"""위아래로 쌓인 패널을 그릴 때 좌우로 배치한다. 패널이 하나면 공식 chart 다.

yaml 예: {use: panel_row}
"""
import matplotlib.pyplot as plt
import numpy as np

from ts2img.charts._render import Style, display_names, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample, names: str | None = None, dpi: int = 100, fmt: str = "jpeg"):
    if sample.kind == "abductive" or len(sample.series) < 2:
        return [fig_to_image(draw(sample, Style(names=names)), dpi=dpi, fmt=fmt)]
    labels = display_names(sample, names)
    series = [np.asarray(s.values, dtype=float) for s in sample.series]
    n = len(series)
    fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 2.4), squeeze=False)
    axes = axes[0]
    for i, values in enumerate(series):
        axes[i].plot(values)
        axes[i].grid(True, alpha=0.3)
        if i < len(labels):
            axes[i].set_title(labels[i], fontsize=9, fontweight="bold")
        axes[i].set_xlabel("Time / Index")
        axes[i].spines["top"].set_visible(False)
        axes[i].spines["right"].set_visible(False)
    fig.tight_layout()
    return [fig_to_image(fig, dpi=dpi, fmt=fmt)]
