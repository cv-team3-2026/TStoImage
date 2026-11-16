"""chart registry. 이 폴더의 .py 파일 하나가 chart 하나다 (밑줄로 시작하는 파일 제외)."""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from functools import lru_cache
from pathlib import Path

from ts2img.charts import post as _post
from ts2img.charts.base import RENDER_LOCK, ChartImage

_SKIP = {"base", "post"}


def chart_names() -> list[str]:
    here = str(Path(__file__).parent)
    return sorted(m.name for m in pkgutil.iter_modules([here]) if not m.name.startswith("_") and m.name not in _SKIP)


@lru_cache(maxsize=None)
def get_chart(name: str):
    if name not in chart_names():
        raise KeyError(f"모르는 chart: {name} (사용 가능: {', '.join(chart_names())})")
    mod = importlib.import_module(f"ts2img.charts.{name}")
    if not hasattr(mod, "render"):
        raise AttributeError(f"charts/{name}.py 에 render(sample, **params) 가 없습니다")
    return mod


def chart_version(name: str) -> int:
    return int(getattr(get_chart(name), "VERSION", 1))


def chart_params(name: str) -> dict:
    """render 의 keyword 인자와 기본값."""
    sig = inspect.signature(get_chart(name).render)
    return {
        k: (None if p.default is inspect.Parameter.empty else p.default)
        for k, p in list(sig.parameters.items())[1:]
        if p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD)
    }


def check_params(name: str, params: dict) -> None:
    sig = inspect.signature(get_chart(name).render)
    if any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values()):
        return
    unknown = set(params) - set(chart_params(name))
    if unknown:
        raise ValueError(
            f"chart '{name}' 에 없는 옵션: {sorted(unknown)} (사용 가능: {sorted(chart_params(name))})"
        )


def render(sample, name: str, params: dict | None = None, post: list | None = None) -> list[ChartImage] | None:
    """chart 를 그리고 후처리를 적용한다."""
    with RENDER_LOCK:
        images = get_chart(name).render(sample, **(params or {}))
    if images is None:
        return None
    if isinstance(images, ChartImage):
        images = [images]
    images = list(images)
    for step in post or []:
        images = [_post.apply(img, step) for img in images]
    return images
