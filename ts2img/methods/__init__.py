"""추론 방식 registry. 새 방식(예: plotting tool 을 쓰는 agent)은 모듈을 만들고 여기에 등록한다."""
from __future__ import annotations

import importlib

_REGISTRY = {
    "single_turn": "ts2img.methods.single_turn",
}


def method_names() -> list[str]:
    return sorted(_REGISTRY)


def get_method(name: str):
    if name not in _REGISTRY:
        raise KeyError(f"모르는 method: {name} (사용 가능: {', '.join(method_names())})")
    return importlib.import_module(_REGISTRY[name])


def method_version(name: str) -> int:
    return int(getattr(get_method(name), "VERSION", 1))
