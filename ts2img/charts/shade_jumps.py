"""변화량이 기준을 넘는 구간의 배경에 옅은 음영만 넣는다.

yaml 예: {use: shade_jumps, z: 2.5}
"""
from ts2img.charts._jumps import points
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def _spans(values, z: float) -> list[tuple[int, int]]:
    idx = points(values, z=z, limit=40)
    if not idx:
        return []
    spans = []
    start = prev = idx[0]
    for i in idx[1:]:
        if i <= prev + 1:
            prev = i
        else:
            spans.append((max(0, start - 1), prev))
            start = prev = i
    spans.append((max(0, start - 1), prev))
    return spans


def render(sample, z: float = 2.5, color: str = "#F2C14E", alpha: float = 0.35, dpi: int = 100, fmt: str = "jpeg"):
    def extra(ax, i, values, line_color):
        for lo, hi in _spans(values, z):
            ax.axvspan(lo, hi, color=color, alpha=alpha, zorder=0)

    return [fig_to_image(draw(sample, Style(), extra), dpi=dpi, fmt=fmt)]
