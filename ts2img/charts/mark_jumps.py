"""변화가 큰 지점의 인덱스를 x축 근처에 작게 표시한다. 음영은 넣지 않는다.

yaml 예: {use: mark_jumps, max_marks: 8}
"""
import numpy as np

from ts2img.charts._jumps import points
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample, z: float = 2.5, max_marks: int = 8, dpi: int = 100, fmt: str = "jpeg"):
    def extra(ax, i, values, line_color):
        marks = points(values, z=z, limit=max_marks)
        if not marks:
            return
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if len(finite) == 0:
            return
        y = float(np.min(finite))
        for idx in marks:
            ax.annotate(
                str(idx), xy=(idx, y), xytext=(0, -2), textcoords="offset points",
                ha="center", va="top", fontsize=6, color="#333333", clip_on=False,
            )

    return [fig_to_image(draw(sample, Style(), extra), dpi=dpi, fmt=fmt)]
