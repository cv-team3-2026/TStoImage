"""벤치마크 공통 형식. 새 벤치마크는 Benchmark 를 상속해 등록한다."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODALITIES = ("text", "vision", "text+vision")


@dataclass
class Series:
    name: str
    values: list[float]


@dataclass
class Sample:
    """문항 하나. chart 와 method 는 벤치마크와 무관하게 이 형식만 본다."""

    id: str                       # "perception#12" (unit#idx)
    unit: str                     # run 폴더 단위. 예: "perception", "reasoning/causal"
    task: str                     # 보고서 집계 단위. 예: "perception/anomaly_detection"
    idx: int
    question: str
    answer: str
    series: list[Series]          # chart 에 그릴 숫자 series
    choices: Any = None
    x: list | None = None         # chart 에서 빠진 시간축 값 (있을 때만)
    x_name: str | None = None
    kind: str = "generic"         # chart 가 구분해 그릴 형태. "generic" | "abductive"
    split_index: int | None = None  # 과거/미래 경계 index (있을 때만)
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class PromptSpec:
    text: str
    schema_name: str = "answer"
    schema_required: tuple[str, ...] = ("reasoning", "answer")

    def response_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string", "description": "Step-by-step reasoning process"},
                "answer": {"type": "string", "description": "Final answer as a single letter"},
            },
            "required": list(self.schema_required),
        }


@dataclass
class Score:
    pred: str | None       # 추출한 답 (대문자 한 글자)
    correct: bool
    parse: str | None      # "json" | "fallback" | None(추출 실패)


@dataclass
class Selection:
    unit: str
    subtasks: frozenset[str] | None = None   # None 이면 unit 전체


class Benchmark:
    name: str = ""
    revision: str = ""
    version: int = 1   # prompt / 로더 동작이 바뀌면 올린다 (run hash 에 포함)

    def units(self) -> list[str]:
        raise NotImplementedError

    def leaf_tasks(self) -> list[str]:
        raise NotImplementedError

    def select(self, path: str) -> list[Selection]:
        """"" / "perception" / "reasoning/causal" 같은 경로를 unit 목록으로 푼다."""
        raise NotImplementedError

    def ensure_data(self, units: list[str] | None = None) -> None:
        raise NotImplementedError

    def root(self):
        """데이터 폴더."""
        raise NotImplementedError

    def has_data(self, unit: str) -> bool:
        raise NotImplementedError

    def n_samples(self, unit: str) -> int | None:
        """데이터를 읽지 않고 알 수 있는 문항 수. 모르면 None."""
        return None

    def load(self, unit: str) -> list[Sample]:
        raise NotImplementedError

    def prompt(self, sample: Sample, modality: str, opts: dict) -> PromptSpec:
        raise NotImplementedError

    def score(self, sample: Sample, response: str) -> Score:
        raise NotImplementedError

    def options(self, sample: Sample) -> list[str]:
        """가능한 정답 글자 목록 (mock 모델과 기준선 계산용)."""
        return ["A", "B", "C", "D"]


def merge_selections(sels: list[Selection]) -> list[Selection]:
    """같은 unit 을 하나로 합친다. 전체 선택(None)이 부분 선택보다 우선한다."""
    merged: dict[str, frozenset[str] | None] = {}
    order: list[str] = []
    for s in sels:
        if s.unit not in merged:
            merged[s.unit] = s.subtasks
            order.append(s.unit)
        elif merged[s.unit] is None or s.subtasks is None:
            merged[s.unit] = None
        else:
            merged[s.unit] = merged[s.unit] | s.subtasks
    return [Selection(u, merged[u]) for u in order]
