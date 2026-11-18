"""시계열 2개 이상을 세로 패널로 그리되 y축 범위를 같게 맞춘다.

1개이거나 abductive 이면 공식 chart 와 같다.
yaml 예: shared_y
"""
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample, dpi: int = 100, fmt: str = "jpeg"):
    style = Style() if sample.kind == "abductive" or len(sample.series) < 2 else Style(share_y=True)
    return [fig_to_image(draw(sample, style), dpi=dpi, fmt=fmt)]
