"""method 공통 형식.

method 모듈 계약:
    VERSION = 1
    def build_request(sample, cell, benchmark, **params) -> Request      # 모델 호출 없이 요청만 만든다
    def run_sample(sample, ctx, **params) -> dict                        # predictions.jsonl 한 줄
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable

from ts2img.benchmarks.base import Benchmark
from ts2img.charts.base import ChartImage
from ts2img.config import Cell
from ts2img.models.client import ChatClient


@dataclass
class Request:
    messages: list
    response_format: dict | None
    prompt_text: str
    images: list[ChartImage] = field(default_factory=list)

    @property
    def prompt_sha(self) -> str:
        return hashlib.sha256(self.prompt_text.encode("utf-8")).hexdigest()[:16]


@dataclass
class RunContext:
    cell: Cell
    benchmark: Benchmark
    client: ChatClient
    capture: Callable | None = None   # (sample, request) 를 받아 예시로 저장하는 hook
