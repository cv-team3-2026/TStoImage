"""공식 chart 에서 선 모양, 크기, 해상도, 이름 표기만 바꾼다.

yaml 예: {use: line_style, linewidth: 4}
         {use: line_style, color: black, dpi: 200, fmt: png}
         {use: line_style, names: "Time Series {n}"}   # perception 의 series_0 표기를 질문과 맞춘다
"""
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(
    sample,
    linewidth: float | None = None,   # None = 공식값
    color: str | None = None,         # None = 공식값. abductive 에는 적용하지 않는다
    scale: float = 1.0,               # figure 크기 배율
    dpi: int = 100,
    fmt: str = "jpeg",                # jpeg | png
    grid: bool = True,
    marker: str | None = None,        # 예: "o", "."
    names: str | None = None,         # 이름 형식. {i}: 0부터, {n}: 1부터, {name}: 원래 이름
):
    style = Style(linewidth=linewidth, color=color, scale=scale, grid=grid, marker=marker, names=names)
    return [fig_to_image(draw(sample, style), dpi=dpi, fmt=fmt)]
