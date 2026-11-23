"""격자 없는 선 그래프를 그리고 그래프 안쪽에만 3x3 계열 필터(sharpen, blur, edge, 침식)를 적용한다.

축선, 눈금 숫자, 축 이름, 제목은 바꾸지 않는다. op: none 은 필터 없이 격자만 뺀 그림이다 (이 chart 끼리의 비교 기준).
yaml 예: {use: inner_filter, op: sharpen}
         {use: inner_filter, op: blur, strength: 1}
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image, pil_to_image

VERSION = 1

OPS = ("none", "sharpen", "blur", "edge", "erode")


def _mask_color(i: int) -> tuple[int, int, int]:
    """패널마다 다른 표시 색. 안쪽 영역을 찾을 때만 쓴다. 이웃 패널과 섞이지 않게 20 단위로 띄운다."""
    return (255, (i // 10 % 12) * 20, 40 + (i % 10) * 20)


def _filter(region: Image.Image, op: str, strength: int) -> Image.Image:
    s = int(strength)
    if op == "sharpen":
        # 수업 과제의 sharpen kernel (중앙 5, 상하좌우 -1) 을 strength 배로 강하게 한 것. 합은 1 이라 밝기가 유지된다
        k = [0, -s, 0, -s, 1 + 4 * s, -s, 0, -s, 0]
        return region.filter(ImageFilter.Kernel((3, 3), k, scale=1))
    if op == "blur":
        return region.filter(ImageFilter.BoxBlur(s))          # (2s+1) x (2s+1) 평균
    if op == "edge":
        # 수업 과제의 edge kernel (Laplacian: 중앙 -4, 상하좌우 1). 밝기에 적용해 절댓값을 취하고 흰 배경으로 뒤집는다
        g = np.pad(np.asarray(region.convert("L"), dtype=float), 1, mode="edge")
        lap = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * g[1:-1, 1:-1]
        e = 255 - np.clip(np.abs(lap) * s, 0, 255).astype(np.uint8)
        return Image.fromarray(np.repeat(e[..., None], 3, axis=2), "RGB")
    if op == "erode":
        return region.filter(ImageFilter.MinFilter(2 * s + 1))  # 침식: 흰 배경의 어두운 선이 굵어진다
    raise ValueError(f"op 는 {', '.join(OPS)} 중 하나: {op}")


def _inner_boxes(sample, dpi: int, n_axes: int) -> list[tuple[int, int, int, int]]:
    """패널별 안쪽 영역 (left, top, right, bottom). 같은 배치로 한 번 더 그려 축 안쪽을 표시 색으로 칠한 뒤 찾는다."""
    def paint(ax, i, values, color):
        c = tuple(v / 255 for v in _mask_color(i))
        ax.set_facecolor(c)
        for line in ax.get_lines():
            line.set_color(c)

    mask = np.asarray(fig_to_image(draw(sample, Style(grid=False), paint), dpi=dpi, fmt="png").pil().convert("RGB")).astype(int)
    boxes = []
    for i in range(n_axes):
        hit = np.abs(mask - np.array(_mask_color(i))).sum(axis=2) <= 6
        ys, xs = np.nonzero(hit)
        if len(xs) == 0:
            continue
        # 왼쪽·아래 축선과 맞닿는 1픽셀은 뺀다
        boxes.append((int(xs.min()) + 1, int(ys.min()), int(xs.max()) + 1, int(ys.max())))
    return boxes


def render(
    sample,
    op: str = "none",        # none | sharpen | blur | edge | erode
    strength: int = 2,       # 1 = 3x3 기본 세기. 2 = sharpen 2배(중앙 9), blur 5x5, edge 세기 2배, 침식 5x5
    dpi: int = 100,
    fmt: str = "png",        # 필터 결과에 압축 흔적이 섞이지 않게 기본은 무손실
):
    if op not in OPS:
        raise ValueError(f"op 는 {', '.join(OPS)} 중 하나: {op}")
    if int(strength) < 1:
        raise ValueError(f"strength 는 1 이상: {strength}")
    base = fig_to_image(draw(sample, Style(grid=False)), dpi=dpi, fmt="png").pil().convert("RGB")
    if op != "none":
        n_axes = 1 if sample.kind == "abductive" else len(sample.series)
        for box in _inner_boxes(sample, dpi, n_axes):
            base.paste(_filter(base.crop(box), op, strength), box[:2])
    return [pil_to_image(base, fmt=fmt)]
