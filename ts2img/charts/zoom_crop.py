"""변화가 가장 큰 구간만 크게 보여 준다. 축과 눈금은 넣지 않는다.

yaml 예: {use: zoom_crop, half: 16}
"""
from ts2img.charts._jumps import window
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image, pil_to_image
from ts2img.charts.post import crop_margin

VERSION = 1


def render(sample, half: int = 16, scale: float = 2.0, dpi: int = 100, fmt: str = "jpeg"):
    lo, hi = window(sample, half)
    fig = draw(sample, Style(scale=scale))
    for ax in fig.axes:
        ax.set_xlim(lo - 0.5, max(lo, hi - 1) + 0.5)
        ax.set_axis_off()
    image = fig_to_image(fig, dpi=dpi, fmt=fmt)
    return [pil_to_image(crop_margin(image.pil()), fmt=fmt, caption=image.caption)]
