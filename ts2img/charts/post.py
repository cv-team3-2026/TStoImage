"""이미지 후처리. 어떤 chart 위에도 얹을 수 있다.

yaml 예: {use: tsrbench_baseline, post: [sharpen]}
         {use: tsrbench_baseline, post: [{use: sharpen, percent: 200}]}
새 필터는 함수를 만들고 FILTERS 에 등록한다. 결과는 PNG(무손실)로 다시 저장한다.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from ts2img.charts.base import ChartImage, pil_to_image

VERSION = 1


def sharpen(img: Image.Image, radius: float = 2, percent: int = 150, threshold: int = 3) -> Image.Image:
    """Unsharp mask."""
    return img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))


def crop_margin(img: Image.Image, white: int = 245, pad: int = 2) -> Image.Image:
    """밝기 임계값으로 내용 범위를 찾아 바깥 흰 여백을 자른다."""
    arr = np.asarray(img.convert("RGB"))
    mask = (arr < white).any(axis=2)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return img
    left = max(0, int(xs.min()) - pad)
    right = min(img.width, int(xs.max()) + 1 + pad)
    top = max(0, int(ys.min()) - pad)
    bottom = min(img.height, int(ys.max()) + 1 + pad)
    return img.crop((left, top, right, bottom))


def axis_sharpen(img: Image.Image, band: float = 0.22, radius: float = 2, percent: int = 180, threshold: int = 3) -> Image.Image:
    """왼쪽과 아래 띠에만 unsharp mask 를 준다."""
    sharp = sharpen(img, radius=radius, percent=percent, threshold=threshold)
    w, h = img.size
    bw = max(1, int(w * band))
    bh = max(1, int(h * band))
    out = img.copy()
    out.paste(sharp.crop((0, 0, bw, h)), (0, 0))
    out.paste(sharp.crop((0, h - bh, w, h)), (0, h - bh))
    return out


def dark_mode(img: Image.Image, white: int = 240) -> Image.Image:
    """배경은 어둡게, 글자는 밝게, 파란 파형은 파란 채로 둔다."""
    arr = np.asarray(img.convert("RGB")).astype(np.int16)
    mn = arr.min(axis=2)
    white_px = mn >= white
    blue = (arr[:, :, 2] > arr[:, :, 0] + 25) & (arr[:, :, 2] > arr[:, :, 1] + 10) & (arr[:, :, 2] > 60)
    out = 255 - arr
    out[white_px] = 22
    out[blue] = np.clip(arr[blue] + 30, 0, 255)
    return Image.fromarray(out.astype(np.uint8), "RGB")


def _long_runs(mask: np.ndarray, min_len: int) -> np.ndarray:
    out = np.zeros(mask.shape, dtype=bool)
    n = len(mask)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i + 1
        while j < n and mask[j]:
            j += 1
        if j - i >= min_len:
            out[i:j] = True
        i = j
    return out


def fade_grid(img: Image.Image, min_frac: float = 0.08) -> Image.Image:
    """길게 이어지는 밝은 회색 수평·수직선만 배경색에 가깝게 만든다."""
    arr = np.asarray(img.convert("RGB")).copy()
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    cand = ((mx - mn) < 18) & (mn > 150) & (mx < 235)
    h, w = cand.shape
    hit = np.zeros_like(cand)
    min_w = max(12, int(w * min_frac))
    min_h = max(8, int(h * min_frac))
    for y in range(h):
        hit[y] |= _long_runs(cand[y], min_w)
    for x in range(w):
        hit[:, x] |= _long_runs(cand[:, x], min_h)
    arr[hit] = 250
    return Image.fromarray(arr, "RGB")


def _saturation(arr: np.ndarray) -> np.ndarray:
    rgb = arr.astype(np.float32)
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


def _dilate_colors(arr: np.ndarray, mask: np.ndarray, radius: int) -> tuple[np.ndarray, np.ndarray]:
    """채도 마스크를 radius 만큼 사각으로 팽창시키고, 새 픽셀은 맞닿은 선의 색을 복사한다."""
    color = arr.copy()
    filled = mask.copy()
    h, w = mask.shape
    shifts = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
    for _ in range(radius):
        added = np.zeros_like(filled)
        nxt = color.copy()
        for dy, dx in shifts:
            ys = slice(max(dy, 0), h + min(dy, 0))
            xs = slice(max(dx, 0), w + min(dx, 0))
            y2 = slice(max(-dy, 0), h + min(-dy, 0))
            x2 = slice(max(-dx, 0), w + min(-dx, 0))
            src_f = np.zeros_like(filled)
            src_c = np.zeros_like(color)
            src_f[y2, x2] = filled[ys, xs]
            src_c[y2, x2] = color[ys, xs]
            take = src_f & ~filled & ~added
            nxt[take] = src_c[take]
            added |= take
        color = nxt
        filled |= added
    return color, filled


def _boost_saturation(arr: np.ndarray, mask: np.ndarray, boost: float) -> np.ndarray:
    rgb = arr.astype(np.float32)
    mx = rgb.max(axis=2, keepdims=True)
    sat = _saturation(arr)
    scale = np.ones(sat.shape, dtype=np.float32)
    strong = sat > 1e-6
    scale[strong] = np.minimum(1.0, sat[strong] * boost) / sat[strong]
    boosted = np.clip(mx - (mx - rgb) * scale[..., None], 0, 255)
    out = rgb.copy()
    out[mask] = boosted[mask]
    return out.astype(np.uint8)


def thicken_line(img: Image.Image, radius: int = 2, sat: float = 0.28, boost: float = 1.3) -> Image.Image:
    """채도 높은 데이터 선만 두껍게 하고 그 선의 채도를 조금 올린다.

    회색 격자, 검은 글자, 흰 배경은 그대로 둔다.
    yaml 예: {use: tsrbench_baseline, post: [thicken_line]}
    """
    arr = np.asarray(img.convert("RGB"))
    rgb = arr.astype(np.float32)
    value = rgb.max(axis=2) / 255.0
    mask = (_saturation(arr) >= sat) & (value >= 0.25)
    if not mask.any() or radius < 1:
        painted, line = arr, mask
    else:
        painted, line = _dilate_colors(arr, mask, int(radius))
    if boost == 1 or not line.any():
        return Image.fromarray(painted, "RGB")
    return Image.fromarray(_boost_saturation(painted, line, boost), "RGB")


FILTERS = {
    "sharpen": sharpen,
    "crop_margin": crop_margin,
    "axis_sharpen": axis_sharpen,
    "dark_mode": dark_mode,
    "fade_grid": fade_grid,
    "thicken_line": thicken_line,
}


def parse(step) -> tuple[str, dict]:
    if isinstance(step, str):
        return step, {}
    step = dict(step)
    name = step.pop("use")
    return name, step


def apply(image: ChartImage, step) -> ChartImage:
    name, params = parse(step)
    if name not in FILTERS:
        raise KeyError(f"모르는 후처리: {name} (사용 가능: {', '.join(FILTERS)})")
    out = FILTERS[name](image.pil().convert("RGB"), **params)
    return pil_to_image(out, fmt="png", caption=image.caption)
