"""여러 series 를 한 축에 겹쳐 그리고 legend 로 구분한다.

공식 chart 는 series 마다 subplot 을 나눈다. 여기서는 색으로 구분해 직접 비교하기 쉽게 한다.
yaml 예: {use: overlay_legend}
         {use: overlay_legend, normalize: zscore, names: "Time Series {n}"}
"""
import matplotlib.pyplot as plt
import numpy as np

from ts2img.charts._render import Style, display_names, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def _normalize(values: np.ndarray, how: str) -> np.ndarray:
    if how == "zscore":
        sd = np.nanstd(values)
        return (values - np.nanmean(values)) / sd if sd > 0 else values - np.nanmean(values)
    if how == "minmax":
        lo, hi = np.nanmin(values), np.nanmax(values)
        return (values - lo) / (hi - lo) if hi > lo else values - lo
    if how == "none":
        return values
    raise ValueError(f"normalize 는 none | zscore | minmax: {how}")


def render(
    sample,
    normalize: str = "none",          # none | zscore | minmax (단위가 다른 series 를 겹칠 때)
    linewidth: float = 1.8,
    width: float = 6,
    height: float = 3,
    legend_loc: str = "best",
    legend_fontsize: float = 8,
    names: str | None = None,
    dpi: int = 100,
    fmt: str = "jpeg",
):
    if sample.kind == "abductive":  # 공식 그림이 이미 겹쳐 그린 형태다
        return [fig_to_image(draw(sample, Style(linewidth=linewidth)), dpi=dpi, fmt=fmt)]

    labels = display_names(sample, names)
    fig, ax = plt.subplots(figsize=(width, height))
    for i, s in enumerate(sample.series):
        values = _normalize(np.asarray(s.values, dtype=float), normalize)
        ax.plot(values, linewidth=linewidth, color=f"C{i % 10}", label=labels[i] or f"series_{i}")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("Time / Index")
    if normalize != "none":
        ax.set_ylabel(f"normalized ({normalize})", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc=legend_loc, fontsize=legend_fontsize, ncol=2 if len(sample.series) > 4 else 1)
    return [fig_to_image(fig, dpi=dpi, fmt=fmt)]
