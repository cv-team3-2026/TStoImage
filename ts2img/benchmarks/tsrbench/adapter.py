"""TSRBench 어댑터: 다운로드, task 계층, 로더.

공식 코드(third_party/TSRBench, commit 084e3f0)와 다르게 동작하는 부분은 CHANGES.md 에 적는다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ts2img.benchmarks.base import Benchmark, PromptSpec, Sample, Score, Selection, Series
from ts2img.benchmarks.tsrbench import prompts, scoring
from ts2img.paths import data_dir

HF_REPO = "umd-zhou-lab/TSRBench"
HF_REVISION = "de20bef327be628cb79fc8f93965ba904470f3fc"


@dataclass(frozen=True)
class Unit:
    file: str      # HF repo 안의 경로
    size: int      # 다운로드 검증용 byte 수
    n: int         # 문항 수

    @property
    def official_name(self) -> str:
        """공식 코드가 task 구분에 쓰는 dataset_name (파일명)."""
        return Path(self.file).stem


UNITS: dict[str, Unit] = {
    "perception": Unit("perception/perception.jsonl", 2708129, 700),
    "reasoning/abductive": Unit("reasoning/abductive_reasoning.jsonl", 5403721, 150),
    "reasoning/causal": Unit("reasoning/causal_reasoning.jsonl", 19514541, 300),
    "reasoning/deductive": Unit("reasoning/deductive_reasoning.jsonl", 2634276, 250),
    "reasoning/etiological": Unit("reasoning/etiological_reasoning.jsonl", 1329080, 350),
    "reasoning/inductive": Unit("reasoning/inductive_reasoning.jsonl", 191817, 100),
    "reasoning/numerical": Unit("reasoning/numerical_reasoning.jsonl", 622168, 400),
    "reasoning/temporal_relation": Unit("reasoning/temporal_relation_reasoning.jsonl", 2069308, 160),
    "prediction/time_series_forecasting": Unit("prediction/time_series_forecasting.jsonl", 7818175, 720),
    "prediction/event_prediction": Unit("prediction/event_prediction.jsonl", 477277, 360),
    "decision/qualitative_decision": Unit("decision/qualitative_decision.jsonl", 83156105, 335),
    "decision/quantitative_decision": Unit("decision/quantitative_decision.jsonl", 857030, 300),
}

# perception 하위 task: 데이터의 category 값 (오타 "Anolmaly" 는 원본 그대로)
PERCEPTION_SUBTASKS = {
    "pattern_recognition": "Pattern Recognition",
    "anomaly_detection": "Anolmaly Detection",
    "similarity_analysis": "Similarity Analysis",
    "noise_understanding": "Noise Understanding",
}
_CATEGORY_TO_SUB = {v: k for k, v in PERCEPTION_SUBTASKS.items()}


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


class TSRBench(Benchmark):
    name = "tsrbench"
    revision = HF_REVISION
    version = 2   # 2: 읽히지 않는 JSON 응답에서 풀이 본문의 글자를 답으로 집지 않는다 (scoring.py)

    # ---- task 계층 -------------------------------------------------------
    def units(self) -> list[str]:
        return list(UNITS)

    def leaf_tasks(self) -> list[str]:
        out = []
        for u in UNITS:
            if u == "perception":
                out += [f"perception/{s}" for s in PERCEPTION_SUBTASKS]
            else:
                out.append(u)
        return out

    def select(self, path: str) -> list[Selection]:
        path = path.strip("/")
        if not path:
            return [Selection(u) for u in UNITS]
        if path in UNITS:
            return [Selection(path)]
        group = [u for u in UNITS if u.startswith(path + "/")]
        if group:
            return [Selection(u) for u in group]
        head, _, sub = path.partition("/")
        if head == "perception" and sub in PERCEPTION_SUBTASKS:
            return [Selection("perception", frozenset({f"perception/{sub}"}))]
        raise KeyError(
            f"tsrbench 에 없는 task: {path!r}\n사용 가능: perception, reasoning, prediction, decision, "
            + ", ".join(self.leaf_tasks())
        )

    # ---- 데이터 ----------------------------------------------------------
    def root(self) -> Path:
        return data_dir() / "tsrbench" / HF_REVISION[:8]

    def path(self, unit: str) -> Path:
        return self.root() / UNITS[unit].file

    def has_data(self, unit: str) -> bool:
        p = self.path(unit)
        return p.is_file() and p.stat().st_size == UNITS[unit].size

    def n_samples(self, unit: str) -> int | None:
        return UNITS[unit].n

    def ensure_data(self, units: list[str] | None = None) -> None:
        """없는 파일만 받는다. revision 을 고정하고 크기로 검증한다."""
        missing = [u for u in (units or self.units()) if not self.has_data(u)]
        if not missing:
            return
        from huggingface_hub import hf_hub_download

        from ts2img import ui

        for u in missing:
            spec = UNITS[u]
            ui.info(f"다운로드: {HF_REPO}/{spec.file} ({spec.size / 1e6:.1f} MB)")
            hf_hub_download(
                HF_REPO, spec.file, repo_type="dataset", revision=HF_REVISION, local_dir=self.root()
            )
            if not self.has_data(u):
                raise RuntimeError(f"다운로드한 파일 크기가 예상과 다릅니다: {self.path(u)}")
        ui.ok(f"데이터 준비 완료: {self.root()}")

    @lru_cache(maxsize=None)
    def load(self, unit: str) -> list[Sample]:
        self.ensure_data([unit])
        rows = []
        with open(self.path(unit), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        if len(rows) != UNITS[unit].n:
            raise RuntimeError(f"{unit}: 문항 수가 예상({UNITS[unit].n})과 다릅니다: {len(rows)}")
        make = self._abductive_sample if unit == "reasoning/abductive" else self._generic_sample
        return [make(unit, i, r) for i, r in enumerate(rows)]

    def _generic_sample(self, unit: str, idx: int, raw: dict) -> Sample:
        ts = raw["timeseries"]
        names = raw.get("name_of_series")
        # 공식 vision 코드: 이름이 없으면 series_{i}, 이름 수가 모자라면 빈 문자열
        chart_names = list(names) if names is not None else [f"series_{i}" for i in range(len(ts))]
        official = UNITS[unit].official_name.lower()

        series, x, x_name = [], None, None
        for i, values in enumerate(ts):
            name = chart_names[i] if i < len(chart_names) else ""
            low = name.strip().lower() if isinstance(name, str) else ""
            # 공식 필터: 시간축 series 는 chart 에 그리지 않는다
            if ("temporal" in official and low == "time stamps") or ("etiological" in official and low == "time"):
                x, x_name = list(values), name
                continue
            series.append(Series(name, [_to_float(v) for v in values]))
        if not series:  # 공식 fallback: 전부 걸러지면 전부 그린다
            series = [
                Series(chart_names[i] if i < len(chart_names) else "", [_to_float(v) for v in values])
                for i, values in enumerate(ts)
            ]
            x, x_name = None, None

        task = unit
        if unit == "perception":
            task = f"perception/{_CATEGORY_TO_SUB[raw['category']]}"
        return Sample(
            id=f"{unit}#{idx}", unit=unit, task=task, idx=idx,
            question=raw["question"], answer=str(raw["answer"]).strip(),
            series=series, choices=raw.get("choices", []), x=x, x_name=x_name, raw=raw,
        )

    def _abductive_sample(self, unit: str, idx: int, raw: dict) -> Sample:
        ts = raw["numerical_time_series"]
        mcq = raw["multiple_choice_question"]
        a_hist, b_hist = ts["wp_Team A"]["history"], ts["wp_Team B"]["history"]
        series = [
            Series("Team A Win Prob", [_to_float(v) for v in a_hist + ts["wp_Team A"]["future"]]),
            Series("Team B Win Prob", [_to_float(v) for v in b_hist + ts["wp_Team B"]["future"]]),
        ]
        return Sample(
            id=f"{unit}#{idx}", unit=unit, task=unit, idx=idx,
            question=mcq["question"], answer=str(mcq["answer"]).strip(),
            series=series, choices=mcq["choices"], kind="abductive", split_index=len(a_hist), raw=raw,
        )

    # ---- prompt / 채점 ---------------------------------------------------
    def prompt(self, sample: Sample, modality: str, opts: dict) -> PromptSpec:
        return prompts.build(sample, modality, opts)

    def score(self, sample: Sample, response: str) -> Score:
        return scoring.score(sample.answer, response)

    def options(self, sample: Sample) -> list[str]:
        return prompts.option_labels(sample)
