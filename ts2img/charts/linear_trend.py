"""원래 선은 그대로 두고 직선 추세선만 얇게 겹친다.

yaml 예: linear_trend
"""
import numpy as np

from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample, dpi: int = 100, fmt: str = "jpeg"):
    def extra(ax, i, values, color):
        y = np.asarray(values, dtype=float)
        x = np.arange(len(y))
        ok = np.isfinite(y)
        if ok.sum() < 2:
            return
        slope, intercept = np.polyfit(x[ok], y[ok], 1)
        ax.plot(x, slope * x + intercept, color="darkorange", linewidth=1.2, label="Linear trend" if i == 0 else None)
        if i == 0 and sample.kind != "abductive":
            ax.legend(loc="best", fontsize=7)

    return [fig_to_image(draw(sample, Style(), extra), dpi=dpi, fmt=fmt)]
