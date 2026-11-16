"""변화가 가장 큰 구간을 원본 수치로 다시 그린다. 그 구간의 인덱스와 값이 남는다.

yaml 예: {use: zoom_window, half: 16}
"""
from ts2img.charts._jumps import window
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample, half: int = 16, dpi: int = 100, fmt: str = "jpeg"):
    lo, hi = window(sample, half)
    fig = draw(sample, Style())
    for ax in fig.axes:
        ax.set_xlim(lo - 0.5, max(lo, hi - 1) + 0.5)
    return [fig_to_image(fig, dpi=dpi, fmt=fmt)]
