"""전체 그림 아래에 앞뒤가 겹치는 두 구간을 원래 plot 크기로 붙인다.

yaml 예: {use: tile_overlap, head: 0.6, tail: 0.6}
"""
from PIL import Image

from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image, pil_to_image

VERSION = 1


def _xlim(sample, lo: int, hi: int, dpi: int, fmt: str) -> Image.Image:
    fig = draw(sample, Style())
    for ax in fig.axes:
        ax.set_xlim(lo - 0.5, max(lo, hi - 1) + 0.5)
    return fig_to_image(fig, dpi=dpi, fmt=fmt).pil().convert("RGB")


def render(sample, head: float = 0.6, tail: float = 0.6, dpi: int = 100, fmt: str = "jpeg"):
    n = max((len(s.values) for s in sample.series), default=0)
    if n < 4:
        return [fig_to_image(draw(sample, Style()), dpi=dpi, fmt=fmt)]
    right = max(2, int(round(n * head)))
    left = min(n - 2, int(round(n * (1 - tail))))
    full = _xlim(sample, 0, n, dpi, fmt)
    front = _xlim(sample, 0, right, dpi, fmt)
    back = _xlim(sample, left, n, dpi, fmt)
    width = front.width + back.width
    height = full.height + max(front.height, back.height)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(full, ((width - full.width) // 2, 0))
    canvas.paste(front, (0, full.height))
    canvas.paste(back, (front.width, full.height))
    return [pil_to_image(canvas, fmt=fmt)]
