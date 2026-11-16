"""TSRBench 공식 line chart. 모든 비교의 기준.

series 1개: 5x2 inch, 파란 선(굵기 2), 제목 = series 이름
여러 개:    세로 subplot, 6 x (개수 x 1.3) inch
abductive:  두 팀 승률을 한 축에 겹쳐 그림 (12x6 inch)
공통:       100 dpi JPEG, bbox tight
"""
from ts2img.charts._render import draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample):
    return [fig_to_image(draw(sample), dpi=100, fmt="jpeg")]
