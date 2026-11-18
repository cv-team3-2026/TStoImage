"""공용 line chart 렌더러.

Style 기본값으로 그리면 TSRBench 공식 그림과 같다.
출처: third_party/TSRBench/inference/vision_opensource/vision_inference_opensource.py (generate_image_from_timeseries),
      vision_inference_opensource_abductive.py (generate_basketball_visualization)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np

from ts2img.benchmarks.base import Sample, Series


@dataclass
class Style:
    linewidth: float | None = None   # None = 공식값 (series 1개: 2, 여러 개: matplotlib 기본 1.5)
    color: str | None = None         # None = 공식값 (series 1개: blue, 여러 개: matplotlib 기본색)
    scale: float = 1.0               # figure 크기 배율
    width_scale: float = 1.0        # 가로만 키운다. 1 이면 공식 폭
    grid: bool = True
    marker: str | None = None
    names: str | None = None         # 이름 형식. 예: "Time Series {n}" ({i}: 0부터, {n}: 1부터, {name}: 원래 이름)
    share_y: bool = False            # 여러 패널의 y축 범위를 같게
    tick_labelsize: float | None = None
    y_ticks: int | None = None       # y축 눈금 개수. None 이면 matplotlib 기본
    panel_height_scales: tuple[float, ...] | None = None  # 패널별 높이 배율. None 이면 공식 높이


# series 를 그린 뒤 호출되는 hook: (ax, series index, values, 선 색)
Extra = Callable[[plt.Axes, int, np.ndarray, str], None]


def display_names(sample: Sample, fmt: str | None) -> list[str]:
    if not fmt:
        return [s.name for s in sample.series]
    return [fmt.format(i=i, n=i + 1, name=s.name) for i, s in enumerate(sample.series)]


def with_values(sample: Sample, fn: Callable[[np.ndarray], np.ndarray]) -> Sample:
    """series 값만 바꾼 Sample 사본."""
    series = [Series(s.name, list(fn(np.asarray(s.values, dtype=float)))) for s in sample.series]
    return replace(sample, series=series)


def rolling_mean(values, window: int) -> np.ndarray:
    """가운데 정렬 이동평균. 양 끝은 있는 값만으로 평균한다 (길이 유지)."""
    a = np.asarray(values, dtype=float)
    w = max(1, int(window))
    if w <= 1 or len(a) == 0:
        return a.copy()
    left, right = (w - 1) // 2, w // 2
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        seg = a[max(0, i - left) : i + right + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg):
            out[i] = seg.mean()
    return out


def _apply_axes(ax, style: Style) -> None:
    if style.tick_labelsize:
        ax.tick_params(axis="both", labelsize=style.tick_labelsize)
    if style.y_ticks:
        ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=int(style.y_ticks)))


def _panel_height(style: Style, n: int, each: float) -> float:
    scales = style.panel_height_scales
    if scales and len(scales) == n:
        return each * sum(scales)
    return each * n


def draw(sample: Sample, style: Style | None = None, extra: Extra | None = None):
    style = style or Style()
    if sample.kind == "abductive":
        return _draw_abductive(sample, style, extra)
    return _draw_generic(sample, style, extra)


def _draw_generic(sample: Sample, style: Style, extra: Extra | None):
    names = display_names(sample, style.names)
    series = [np.asarray(s.values, dtype=float) for s in sample.series]
    k = style.scale

    if len(series) == 1:
        fig, ax = plt.subplots(figsize=(5 * k * style.width_scale, _panel_height(style, 1, 2 * k)))
        color = style.color or "blue"
        ax.plot(series[0], linewidth=style.linewidth or 2, color=color, marker=style.marker)
        if style.grid:
            ax.grid(True)
        if names:
            ax.set_title(names[0], fontsize=10, fontweight="bold")
        ax.set_xlabel("Time / Index")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if extra:
            extra(ax, 0, series[0], color)
        _apply_axes(ax, style)
        return fig

    fig, axes = plt.subplots(len(series), 1, figsize=(6 * k * style.width_scale, _panel_height(style, len(series), 1.3 * k)))
    axes = np.atleast_1d(axes)
    for i, values in enumerate(series):
        kw = {}
        if style.linewidth:
            kw["linewidth"] = style.linewidth
        if style.color:
            kw["color"] = style.color
        if style.marker:
            kw["marker"] = style.marker
        (line,) = axes[i].plot(values, **kw)
        if style.grid:
            axes[i].grid(True, alpha=0.3)
        if i < len(names):
            axes[i].set_ylabel(names[i], fontsize=9, fontweight="bold")
        axes[i].set_xlabel("Time / Index")
        axes[i].spines["top"].set_visible(False)
        axes[i].spines["right"].set_visible(False)
        if extra:
            extra(axes[i], i, values, line.get_color())
        _apply_axes(axes[i], style)
    if style.share_y:
        finite = [v[np.isfinite(v)] for v in series if np.isfinite(v).any()]
        if finite:
            lo = min(float(v.min()) for v in finite)
            hi = max(float(v.max()) for v in finite)
            pad = (hi - lo) * 0.05 or 1.0
            for ax in axes:
                ax.set_ylim(lo - pad, hi + pad)
    return fig


def _draw_abductive(sample: Sample, style: Style, extra: Extra | None):
    """두 팀 승률. 실선 = 과거, 점선 = 미래, 초록 세로선 = critical moment."""
    a = np.asarray(sample.series[0].values, dtype=float)
    b = np.asarray(sample.series[1].values, dtype=float)
    split = sample.split_index or 0
    total = len(a)
    x = np.arange(total)
    lw = style.linewidth or 2
    k = style.scale

    fig, ax = plt.subplots(figsize=(12 * k * style.width_scale, 6 * k))
    ax.plot(x[:split], a[:split], "b-", linewidth=lw, label="Team A Win Prob (History)", alpha=0.8)
    ax.plot(x[split:], a[split:], "b--", linewidth=lw, label="Team A Win Prob (Future)", alpha=0.8)
    ax.plot(x[:split], b[:split], "r-", linewidth=lw, label="Team B Win Prob (History)", alpha=0.8)
    ax.plot(x[split:], b[split:], "r--", linewidth=lw, label="Team B Win Prob (Future)", alpha=0.8)
    ax.axvline(x=split, color="green", linestyle="--", linewidth=2, alpha=0.7, label="Critical Moment")
    if extra:
        extra(ax, 0, a, "blue")
        extra(ax, 1, b, "red")
    ax.set_xlim(0, total)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Event Index", fontsize=11)
    ax.set_ylabel("Win Probability", fontsize=11)
    ax.set_title("Win Probability Evolution", fontsize=14, fontweight="bold")
    ax.legend(loc="best", fontsize=9)
    if style.grid:
        ax.grid(True, alpha=0.3)
    _apply_axes(ax, style)
    fig.tight_layout()
    return fig
