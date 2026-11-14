"""이미지 후처리. 어떤 chart 위에도 얹을 수 있다.

yaml 예: {use: tsrbench_baseline, post: [sharpen]}
         {use: tsrbench_baseline, post: [{use: sharpen, percent: 200}]}
새 필터는 함수를 만들고 FILTERS 에 등록한다. 결과는 PNG(무손실)로 다시 저장한다.
"""
from __future__ import annotations

from PIL import Image, ImageFilter

from ts2img.charts.base import ChartImage, pil_to_image

VERSION = 1


def sharpen(img: Image.Image, radius: float = 2, percent: int = 150, threshold: int = 3) -> Image.Image:
    """Unsharp mask."""
    return img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))


FILTERS = {
    "sharpen": sharpen,
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
