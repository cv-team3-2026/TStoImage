"""데이터 선만 격자와 구분되는 색으로 바꾼다. 배경 밝기는 그대로다.

yaml 예: {use: recolor_line, color: "#E4572E"}
"""
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1

_PALETTE = ("#E4572E", "#1B9E77", "#7570B3", "#E6AB02", "#666666")


def render(sample, color: str = "#E4572E", dpi: int = 100, fmt: str = "jpeg"):
    palette = (color, *_PALETTE[1:])

    def extra(ax, i, values, line_color):
        lines = [ln for ln in ax.get_lines() if ln.get_label() != "Critical Moment"]
        if sample.kind == "abductive":
            if i == 0:
                for k, ln in enumerate(lines):
                    ln.set_color(palette[0] if k < 2 else palette[1])
            return
        if lines:
            lines[-1].set_color(palette[i % len(palette)])

    return [fig_to_image(draw(sample, Style(), extra), dpi=dpi, fmt=fmt)]
