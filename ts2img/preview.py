"""모델을 부르지 않고 chart 와 prompt 를 미리 본다."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from ts2img.benchmarks import get_benchmark
from ts2img.benchmarks.base import Sample, Series
from ts2img.config import ChartSpec, Experiment, expand, load_experiment
from ts2img.methods import get_method
from ts2img.paths import ROOT, results_dir
from ts2img.report.build import _grid_figure, _render
from ts2img.runner import select_samples

EXAMPLES_DIR = ROOT / "augmentation_examples"


def parse_charts(items: list[str] | None, exp: Experiment | None = None) -> list[ChartSpec]:
    """CLI 인자 -> ChartSpec. 예: tsrbench_baseline  "{use: line_style, linewidth: 4}" """
    if not items:
        return list(exp.charts) if exp else [ChartSpec("tsrbench_baseline")]
    return [ChartSpec.parse(yaml.safe_load(s)) for s in items]


def example_samples() -> list[Sample]:
    """augmentation_examples/ 의 예시 9개를 Sample 로 읽는다."""
    out = []
    for i, d in enumerate(sorted(p for p in EXAMPLES_DIR.iterdir() if (p / "data.json").is_file())):
        data = json.loads((d / "data.json").read_text(encoding="utf-8"))
        series = [Series(n, [float(v) for v in vals]) for n, vals in zip(data["name_of_series"], data["timeseries"])]
        out.append(Sample(id=f"example#{i}", unit="example", task=d.name, idx=i, question="", answer="",
                          series=series, x=data.get("timestamps"), raw=data))
    return out


def task_samples(task: str, limit: int | None = None) -> list[Sample]:
    """"tsrbench/perception/anomaly_detection" 같은 선택자에 해당하는 문항."""
    exp = Experiment(name="preview", benchmarks=[task], models=["mock"], modalities=["vision"], limit=limit)
    out = []
    for cell in expand(exp):
        out += select_samples(cell)
    return out


def chart_gallery(charts: list[ChartSpec], samples: list[Sample], out: Path | None = None) -> Path:
    """행 = chart, 열 = 문항 인 격자 그림을 저장한다."""
    out = out or results_dir() / "preview" / "charts.png"
    cells = [[_render(s, c) for s in samples] for c in charts]
    _grid_figure(cells, [c.label for c in charts], [f"{s.task} #{s.idx}" for s in samples], out)
    return out


def prompt_preview(task: str, modality: str = "vision", chart: ChartSpec | None = None, pos: int = 0,
                   exp_path: Path | None = None, model: str | None = None) -> dict:
    """모델에 실제로 들어갈 요청을 만든다. pos = 선택된 문항 중 몇 번째인지."""
    base = load_experiment(exp_path) if exp_path else None
    exp = Experiment(
        name="preview", benchmarks=[task], models=[model or (base.models[0] if base else "mock")], modalities=[modality],
        charts=[chart or (base.charts[0] if base else ChartSpec("tsrbench_baseline"))],
        **({k: getattr(base, k) for k in ("method", "sampling", "max_tokens", "response_format", "text_stride")} if base else {}),
    )
    cell = expand(exp)[0]
    samples = select_samples(cell)
    sample = samples[pos]
    method = get_method(exp.method["use"])
    params = {k: v for k, v in exp.method.items() if k != "use"}
    req = method.build_request(sample, cell, get_benchmark(cell.benchmark), **params)

    out_dir = results_dir() / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, im in enumerate(req.images):
        p = out_dir / f"prompt_image_{k}.{im.ext}"
        p.write_bytes(im.data)
        paths.append(p)
    from ts2img.models.client import request_kwargs

    kwargs = request_kwargs(
        cell.model, [], response_format=req.response_format,
        sampling=exp.sampling_params(0), max_tokens=exp.max_tokens,
    )
    kwargs.pop("messages")
    return {
        "sample": sample, "cell": cell, "text": req.prompt_text, "image_paths": paths, "images": req.images,
        "content_order": [p["type"] if p["type"] == "image_url" else "text" for p in req.messages[0]["content"]],
        "captions": [im.caption for im in req.images], "request": kwargs, "n_selected": len(samples),
    }


def print_prompt(info: dict, max_chars: int = 6000) -> None:
    from ts2img import ui

    s, cell = info["sample"], info["cell"]
    request = {k: (v if k != "response_format" else v.get("type")) for k, v in info["request"].items()}
    sent = [k for k in ("temperature", "top_p", "seed") if k in info["request"]]
    ui.kv_table("요청 정보", [
        ("문항", f"{cell.benchmark}/{s.task} #{s.idx} (선택된 {info['n_selected']}개 중)"),
        ("정답", s.answer),
        ("model", f"{cell.model.key} ({cell.model.model})"),
        ("입력 조건", cell.modality),
        ("chart", cell.chart.label if "vision" in cell.modality else "(text 조건: chart 없음)"),
        ("message 구성", " -> ".join(info["content_order"])),
        ("요청 옵션", request),
        ("sampling", ", ".join(sent) + " 를 보냄" if sent else "보내지 않음 (서버 기본값 사용. 공식 코드와 같음)"),
        ("text 길이", f"{len(info['text'])}자"),
    ])
    text = info["text"]
    if len(text) > max_chars:
        half = max_chars // 2
        text = text[:half] + f"\n\n... ({len(info['text']) - max_chars}자 생략) ...\n\n" + text[-half:]
    ui.console.rule("text (모델에 들어가는 그대로)")
    ui.console.print(text, markup=False, highlight=False, soft_wrap=True)
    ui.console.rule()
    for k, im in enumerate(info["images"]):
        w, h = im.size
        cap = f" | caption: {im.caption}" if im.caption else ""
        ui.info(f"이미지 {k + 1}: {w}x{h}px, {len(im.data) / 1024:.0f} KB, {im.mime}{cap} -> {info['image_paths'][k]}")
    if not info["images"]:
        ui.info("이미지 없음")
