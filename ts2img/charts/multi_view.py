"""같은 시계열을 다른 관점으로 그린 이미지를 여러 장 보낸다.

views 에 적은 순서대로 이미지를 만든다. 각 이미지에는 caption 이 붙어 모델에 함께 전달된다.
yaml 예: {use: multi_view, views: [full, smooth]}
         {use: multi_view, views: [full, smooth, diff], window: 12}
"""
import numpy as np

from ts2img.charts._render import Style, draw, rolling_mean, with_values
from ts2img.charts.base import fig_to_image

VERSION = 1


def _diff(values: np.ndarray) -> np.ndarray:
    return np.diff(values, prepend=values[:1]) if len(values) else values


def render(
    sample,
    views: tuple = ("full", "smooth"),   # full | smooth | diff
    window: int = 8,                     # smooth 의 이동평균 구간
    names: str | None = None,
    dpi: int = 100,
    fmt: str = "jpeg",
):
    makers = {
        "full": (lambda: sample, "Original time series"),
        "smooth": (
            lambda: with_values(sample, lambda v: rolling_mean(v, window)),
            f"Smoothed with a moving average (window={window})",
        ),
        "diff": (lambda: with_values(sample, _diff), "First difference (change between consecutive points)"),
    }
    images = []
    for view in views:
        if view not in makers:
            raise ValueError(f"views 는 {sorted(makers)} 중에서 고른다: {view}")
        make, caption = makers[view]
        images.append(fig_to_image(draw(make(), Style(names=names)), dpi=dpi, fmt=fmt, caption=caption))
    return images
