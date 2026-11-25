"""가로 배치, 공유 y축, 배율, 급변 음영을 한 그림에서 고른다.

ablation 용. series 가 하나이거나 abductive 이면 공식 chart 에 배율과 음영만 적용한다.
yaml 예: {use: combo, layout: row, share_y: true, scale: 3, shade: true, post: [fade_grid, dark_mode]}
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from ts2img.charts._render import Style, display_names, draw
from ts2img.charts.base import fig_to_image
from ts2img.charts.shade_jumps import _spans

VERSION = 1

_LAYOUTS = {"row", "stack"}


def render(
    sample,
    layout: str = "row",
    share_y: bool = False,
    scale: float = 1.0,
    shade: bool = False,
    z: float = 2.5,
    dpi: int = 100,
    fmt: str = "jpeg",
):
    if layout not in _LAYOUTS:
        raise ValueError(f"layout 은 row 또는 stack: {layout}")
    extra = _shade(z) if shade else None
    if sample.kind == "abductive" or len(sample.series) < 2 or layout == "stack":
        style = Style(scale=float(scale), share_y=bool(share_y) and layout == "stack")
        return [fig_to_image(draw(sample, style, extra), dpi=dpi, fmt=fmt)]
    return [fig_to_image(_draw_row(sample, float(scale), extra, share_y=bool(share_y)), dpi=dpi, fmt=fmt)]


def _shade(z: float):
    def extra(ax, i, values, line_color):
        for lo, hi in _spans(values, z):
            ax.axvspan(lo, hi, color="#F2C14E", alpha=0.35, zorder=0)

    return extra


def _draw_row(sample, scale: float, extra, share_y: bool):
    labels = display_names(sample, None)
    series = [np.asarray(s.values, dtype=float) for s in sample.series]
    n = len(series)
    fig, axes = plt.subplots(1, n, figsize=(3.2 * n * scale, 2.4 * scale), squeeze=False)
    axes = axes[0]
    for i, values in enumerate(series):
        (line,) = axes[i].plot(values)
        axes[i].grid(True, alpha=0.3)
        if i < len(labels):
            axes[i].set_title(labels[i], fontsize=9, fontweight="bold")
        axes[i].set_xlabel("Time / Index")
        axes[i].spines["top"].set_visible(False)
        axes[i].spines["right"].set_visible(False)
        if extra:
            extra(axes[i], i, values, line.get_color())
    if share_y:
        finite = [v[np.isfinite(v)] for v in series if np.isfinite(v).any()]
        if finite:
            lo = min(float(v.min()) for v in finite)
            hi = max(float(v.max()) for v in finite)
            pad = (hi - lo) * 0.05 or 1.0
            for ax in axes:
                ax.set_ylim(lo - pad, hi + pad)
    fig.tight_layout()
    return fig
