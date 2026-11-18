"""한 칸의 평균 기울기가 약 45도가 되도록 패널 높이를 맞춘다.

가로 폭은 공식 chart 와 같다. 평평한 선은 공식 높이를 유지한다.
yaml 예: aspect
"""
import numpy as np

from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1


def _height_scale(values, base_w: float, base_h: float) -> float:
    y = np.asarray(values, dtype=float)
    y = y[np.isfinite(y)]
    if len(y) < 2:
        return 1.0
    span = float(y.max() - y.min())
    step = float(np.mean(np.abs(np.diff(y))))
    if span < 1e-9 or step < 1e-12:
        return 1.0
    height = base_w * span / (step * (len(y) - 1))
    return float(np.clip(height / base_h, 0.35, 4.0))


def render(sample, dpi: int = 100, fmt: str = "jpeg"):
    if sample.kind == "abductive" or not sample.series:
        return [fig_to_image(draw(sample), dpi=dpi, fmt=fmt)]
    if len(sample.series) == 1:
        scales = (_height_scale(sample.series[0].values, 5.0, 2.0),)
    else:
        scales = tuple(_height_scale(s.values, 6.0, 1.3) for s in sample.series)
    return [fig_to_image(draw(sample, Style(panel_height_scales=scales)), dpi=dpi, fmt=fmt)]
