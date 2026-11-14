"""yaml 설정 로더와 실험 cell 전개.

cell = (benchmark unit, model, modality, chart, repeat) 조합 하나 = run 폴더 하나.
run 폴더 이름의 hash 는 "같은 문항에 같은 답이 나오는 조건"만으로 만든다.
문항 선택(limit, 하위 task)과 실행 옵션(concurrency 등)은 hash 에 넣지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ts2img import benchmarks, charts
from ts2img.benchmarks.base import MODALITIES
from ts2img.charts import post as chart_post
from ts2img.paths import CONFIGS, runs_dir

IDENTITY_VERSION = 1

# serve 블록에서 결과와 무관한 운영용 값 (hash 제외).
# max_model_len 은 한도 안에 들어오는 문항의 답을 바꾸지 않는다. 넘는 문항은 context_overflow 로 따로 기록되고,
# 한도를 올리면 그 문항만 다시 시도한다 (runner.is_done).
_SERVE_OPERATIONAL = {"port", "host", "gpus", "gpu_memory_utilization", "startup_timeout_s", "env", "max_model_len"}


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]+", "-", text).strip("-")


# ---- model -----------------------------------------------------------------
@dataclass
class ModelSpec:
    key: str
    model: str                          # API 에 보내는 model 이름
    provider: str = "openai"            # openai (OpenAI-compatible) | mock
    base_url: str | None = None
    base_url_env: str | None = None     # URL 을 secrets 에서 읽을 때
    api_key_env: str | None = None
    paid: bool = False                  # 유료 API. true 면 run 에 --budget-usd 가 필요하다
    request: dict = field(default_factory=dict)   # 모든 요청에 붙는 값 (reasoning_effort, extra_body ...)
    max_tokens_param: str = "max_tokens"          # 일부 상용 모델은 max_completion_tokens
    response_format: str | None = None            # 실험 설정을 덮어쓸 때
    serve: dict | None = None           # 있으면 직접 띄우는 모델
    notes: str = ""

    def identity(self) -> dict:
        serve = None
        if self.serve:
            serve = {k: v for k, v in sorted(self.serve.items()) if k not in _SERVE_OPERATIONAL}
        return {"key": self.key, "model": self.model, "provider": self.provider, "request": self.request, "serve": serve}

    @property
    def context_limit(self) -> int | None:
        """직접 띄우는 모델의 context 한도. 외부 endpoint 는 알 수 없어 None."""
        return (self.serve or {}).get("max_model_len")

    def resolved_base_url(self) -> str | None:
        from ts2img import secrets

        if self.base_url_env:
            return secrets.get(self.base_url_env)
        if self.base_url:
            return self.base_url
        if self.serve:
            return f"http://{self.serve.get('host', '127.0.0.1')}:{self.serve.get('port', 8000)}/v1"
        return None


def load_models(path: Path | None = None) -> dict[str, ModelSpec]:
    # TS2IMG_MODELS_FILE: 다른 models.yaml 을 쓸 때 (테스트, 개인용 설정)
    path = path or Path(os.environ.get("TS2IMG_MODELS_FILE") or CONFIGS / "models.yaml")
    raw = _load_yaml(path).get("models") or {}
    out = {}
    for key, cfg in raw.items():
        cfg = dict(cfg or {})
        unknown = set(cfg) - set(ModelSpec.__dataclass_fields__)
        if unknown:
            raise ValueError(f"models.yaml '{key}' 에 모르는 항목: {sorted(unknown)}")
        out[key] = ModelSpec(key=key, **cfg)
    # 네트워크 없이 흐름을 확인하는 가짜 모델은 항상 쓸 수 있다
    out.setdefault("mock", ModelSpec(key="mock", model="mock", provider="mock", notes="가짜 응답 (흐름 확인용)"))
    return out


def load_pricing(path: Path | None = None) -> dict[str, dict]:
    p = path or CONFIGS / "pricing.yaml"
    return (_load_yaml(p).get("prices") or {}) if p.is_file() else {}


# ---- chart -----------------------------------------------------------------
@dataclass
class ChartSpec:
    use: str
    params: dict = field(default_factory=dict)
    post: list = field(default_factory=list)
    label_override: str | None = None

    @classmethod
    def parse(cls, raw) -> "ChartSpec":
        if isinstance(raw, str):
            spec = cls(raw)
        else:
            d = dict(raw)
            if "use" not in d:
                raise ValueError(f"chart 항목에 use 가 없습니다: {raw}")
            spec = cls(d.pop("use"), post=list(d.pop("post", []) or []), label_override=d.pop("label", None), params=d)
        charts.check_params(spec.use, spec.params)
        for step in spec.post:
            name, _ = chart_post.parse(step)
            if name not in chart_post.FILTERS:
                raise ValueError(f"모르는 후처리: {name}")
        return spec

    @property
    def label(self) -> str:
        if self.label_override:
            return self.label_override
        s = self.use
        if self.params:
            s += "(" + ", ".join(f"{k}={_short(v)}" for k, v in self.params.items()) + ")"
        for step in self.post:
            name, params = chart_post.parse(step)
            s += f"+{name}" + ("(" + ", ".join(f"{k}={v}" for k, v in params.items()) + ")" if params else "")
        return s

    @property
    def slug(self) -> str:
        return _slug(self.label.replace("(", "-").replace(")", "").replace("=", "").replace(", ", "-"))[:60]

    def identity(self) -> dict:
        return {
            "use": self.use,
            "params": self.params,
            "post": [list(chart_post.parse(s)) for s in self.post],
            "version": charts.chart_version(self.use),
            "post_version": chart_post.VERSION if self.post else None,
        }


def _short(v) -> str:
    if isinstance(v, (list, tuple)):
        return "+".join(str(x) for x in v)
    return str(v)


NONE_CHART = ChartSpec("none")


# ---- experiment ------------------------------------------------------------
@dataclass
class Experiment:
    name: str
    benchmarks: list[str]
    models: list[str]
    modalities: list[str] = field(default_factory=lambda: ["vision"])
    charts: list[ChartSpec] = field(default_factory=lambda: [ChartSpec("tsrbench_baseline")])
    method: dict = field(default_factory=lambda: {"use": "single_turn"})
    sampling: Any = "official"          # official | deterministic | {temperature: ..., top_p: ..., seed: ...}
    repeats: int = 1
    max_tokens: int | None = None       # None = 보내지 않는다 (공식 방식). 서버가 context 가 허용하는 만큼 생성한다
    response_format: str = "json_schema"  # json_schema | json_object | none
    answer_retries: int = 10            # 답 글자를 못 찾으면 다시 요청하는 횟수 (공식 10)
    text_stride: Any = 1                # text 값 간격. 1 = 전체, "gpt_official" = 공식 GPT용 방식
    ts_placeholder: str = "keep"        # 이미지를 넣는 조건에서 질문 속 "<ts><ts/>" 처리. keep = 그대로(공식), 그 외 = 이 문자열로 바꿈
    limit: int | None = None            # unit 마다 앞에서 N 문항만
    concurrency: int = 8
    request_timeout: float = 1800       # 요청 하나의 제한 시간(초). max_tokens 상한이 없으면 응답 하나가 10분을 넘을 수 있다
    baseline: str | None = None         # 보고서 비교 기준 chart label. 없으면 charts 의 첫 항목
    description: str = ""
    source: Path | None = None

    def sampling_params(self, repeat: int = 0) -> dict:
        """요청에 실제로 넣는 sampling 값. official 은 아무것도 보내지 않는다."""
        if self.sampling == "official":
            return {}
        if self.sampling == "deterministic":
            params = {"temperature": 0, "seed": 0}
        elif isinstance(self.sampling, dict):
            params = dict(self.sampling)
        else:
            raise ValueError(f"sampling 은 official | deterministic | dict: {self.sampling}")
        if "seed" in params and params["seed"] is not None:
            params["seed"] = int(params["seed"]) + repeat
        return params

    @property
    def deterministic(self) -> bool:
        return self.sampling_params().get("temperature") == 0

    def baseline_label(self) -> str:
        return self.baseline or self.charts[0].label


def load_experiment(path: Path) -> Experiment:
    raw = _load_yaml(path)
    fields = set(Experiment.__dataclass_fields__) - {"source"}
    unknown = set(raw) - fields
    if unknown:
        raise ValueError(f"{path.name} 에 모르는 항목: {sorted(unknown)} (사용 가능: {sorted(fields)})")
    for req in ("benchmarks", "models"):
        if not raw.get(req):
            raise ValueError(f"{path.name}: {req} 가 비어 있습니다")
    raw.setdefault("name", path.stem)
    if "charts" in raw:
        raw["charts"] = [ChartSpec.parse(c) for c in raw["charts"]]
    if isinstance(raw.get("method"), str):
        raw["method"] = {"use": raw["method"]}
    exp = Experiment(source=path, **raw)
    for m in exp.modalities:
        if m not in MODALITIES:
            raise ValueError(f"모르는 modality: {m} (사용 가능: {', '.join(MODALITIES)})")
    if exp.response_format not in ("json_schema", "json_object", "none"):
        raise ValueError(f"response_format: {exp.response_format}")
    exp.sampling_params()  # 형식 검증
    labels = [c.label for c in exp.charts]
    if len(set(labels)) != len(labels):
        raise ValueError(f"charts 에 같은 항목이 두 번 있습니다: {labels}")
    return exp


# ---- cell ------------------------------------------------------------------
@dataclass
class Cell:
    exp: Experiment
    benchmark: str
    unit: str
    subtasks: frozenset | None
    model: ModelSpec
    modality: str
    chart: ChartSpec
    repeat: int = 0

    def prompt_opts(self) -> dict:
        opts = {"text_stride": self.exp.text_stride}
        if self.exp.ts_placeholder != "keep":
            opts["ts_placeholder"] = self.exp.ts_placeholder
        return opts

    def response_format(self) -> str:
        return self.model.response_format or self.exp.response_format

    def identity(self) -> dict:
        from ts2img import methods

        bench = benchmarks.get_benchmark(self.benchmark)
        method = dict(self.exp.method)
        return {
            "v": IDENTITY_VERSION,
            "benchmark": {"name": self.benchmark, "revision": bench.revision, "version": bench.version, "unit": self.unit},
            "model": self.model.identity(),
            "modality": self.modality,
            "chart": self.chart.identity(),
            "method": {**method, "version": methods.method_version(method["use"])},
            "sampling": self.exp.sampling_params(self.repeat) or "official",
            "max_tokens": self.exp.max_tokens,
            "response_format": self.response_format(),
            "answer_retries": self.exp.answer_retries,
            "prompt": self.prompt_opts(),
            "repeat": self.repeat,
        }

    @property
    def hash(self) -> str:
        blob = json.dumps(self.identity(), sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]

    @property
    def run_dir(self) -> Path:
        leaf = f"{self.chart.slug}__{self.hash}" + (f"__r{self.repeat}" if self.repeat else "")
        return runs_dir() / self.benchmark / self.unit / _slug(self.model.key) / self.modality / leaf

    @property
    def label(self) -> str:
        r = f" r{self.repeat}" if self.repeat else ""
        return f"{self.benchmark}/{self.unit} | {self.model.key} | {self.modality} | {self.chart.label}{r}"


def expand(exp: Experiment, models: dict[str, ModelSpec] | None = None) -> list[Cell]:
    """실험을 cell 목록으로 푼다. text 조건은 chart 와 무관하므로 cell 하나로 합친다."""
    models = models or load_models()
    for key in exp.models:
        if key not in models:
            raise KeyError(f"models.yaml 에 없는 모델: {key} (사용 가능: {', '.join(models)})")
    cells, seen = [], set()
    for bench, selections in benchmarks.resolve(exp.benchmarks).items():
        for sel in selections:
            for mkey in exp.models:
                for modality in exp.modalities:
                    for chart in [NONE_CHART] if modality == "text" else exp.charts:
                        for r in range(max(1, exp.repeats)):
                            cell = Cell(exp, bench, sel.unit, sel.subtasks, models[mkey], modality, chart, r)
                            if cell.run_dir not in seen:
                                seen.add(cell.run_dir)
                                cells.append(cell)
    return cells
