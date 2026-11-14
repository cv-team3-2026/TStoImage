"""벤치마크 registry. 새 벤치마크를 추가하면 _REGISTRY 에 등록한다."""
from __future__ import annotations

from functools import lru_cache

from ts2img.benchmarks.base import Benchmark, Selection, merge_selections

_REGISTRY = {
    "tsrbench": "ts2img.benchmarks.tsrbench.adapter:TSRBench",
}


def benchmark_names() -> list[str]:
    return sorted(_REGISTRY)


@lru_cache(maxsize=None)
def get_benchmark(name: str) -> Benchmark:
    if name not in _REGISTRY:
        raise KeyError(f"모르는 벤치마크: {name} (사용 가능: {', '.join(benchmark_names())})")
    module, cls = _REGISTRY[name].split(":")
    import importlib

    return getattr(importlib.import_module(module), cls)()


def resolve(selectors: list[str]) -> dict[str, list[Selection]]:
    """["tsrbench/perception", "tsrbench/reasoning/causal"] -> {benchmark: [Selection, ...]}"""
    out: dict[str, list[Selection]] = {}
    for sel in selectors:
        name, _, path = sel.strip().strip("/").partition("/")
        out.setdefault(name, []).extend(get_benchmark(name).select(path))
    return {k: merge_selections(v) for k, v in out.items()}
