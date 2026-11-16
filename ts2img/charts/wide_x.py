"""높이는 유지하고 가로만 늘려 다시 그린다.

yaml 예: {use: wide_x, width: 2}
"""
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample, width: float = 2.0, dpi: int = 100, fmt: str = "jpeg"):
    return [fig_to_image(draw(sample, Style(width_scale=width)), dpi=dpi, fmt=fmt)]
