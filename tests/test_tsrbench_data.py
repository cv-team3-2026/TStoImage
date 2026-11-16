"""TSRBench 15개 task 전체(4,125문항)에 대해 로더, prompt, chart 가 동작하는지 확인한다.

데이터가 없으면 처음 한 번 내려받는다 (약 130MB).
chart 전수 렌더링은 오래 걸려 기본으로는 일부만 한다. 전부 하려면: TS2IMG_FULL=1 pytest tests/test_tsrbench_data.py
"""
import os
from collections import Counter

import pytest

from ts2img import charts
from ts2img.benchmarks import get_benchmark
from ts2img.benchmarks.base import MODALITIES
from ts2img.benchmarks.tsrbench.adapter import UNITS
from ts2img.config import ChartSpec

BENCH = get_benchmark("tsrbench")
ALL_CHARTS = [
    ChartSpec.parse("tsrbench_baseline"),
    ChartSpec.parse({"use": "line_style", "linewidth": 4, "color": "black", "scale": 1.5, "marker": "o", "grid": False, "names": "Time Series {n}"}),
    ChartSpec.parse({"use": "line_style", "fmt": "png", "post": ["sharpen"]}),
    ChartSpec.parse({"use": "moving_average", "window": 8}),
    ChartSpec.parse({"use": "overlay_legend", "normalize": "zscore"}),
    ChartSpec.parse({"use": "overlay_legend", "normalize": "minmax"}),
    ChartSpec.parse({"use": "multi_view", "views": ["full", "smooth", "diff"]}),
    ChartSpec.parse({"use": "tsrbench_baseline", "post": ["crop_margin"]}),
    ChartSpec.parse({"use": "tsrbench_baseline", "post": ["axis_sharpen"]}),
    ChartSpec.parse({"use": "tsrbench_baseline", "post": ["dark_mode"]}),
    ChartSpec.parse({"use": "tsrbench_baseline", "post": ["fade_grid"]}),
    ChartSpec.parse("tile_overlap"),
    ChartSpec.parse("panel_row"),
    ChartSpec.parse("zoom_crop"),
    ChartSpec.parse("zoom_window"),
    ChartSpec.parse({"use": "wide_x", "width": 2}),
    ChartSpec.parse("recolor_line"),
    ChartSpec.parse("shade_jumps"),
    ChartSpec.parse("mark_jumps"),
]


@pytest.fixture(scope="module")
def data():
    return {u: BENCH.load(u) for u in BENCH.units()}


def test_counts(data):
    assert sum(len(v) for v in data.values()) == 4125
    assert {u: len(v) for u, v in data.items()} == {u: spec.n for u, spec in UNITS.items()}
    sub = Counter(s.task for s in data["perception"])
    assert sub == {"perception/pattern_recognition": 371, "perception/anomaly_detection": 129,
                   "perception/similarity_analysis": 113, "perception/noise_understanding": 87}
    ids = [s.id for v in data.values() for s in v]
    assert len(set(ids)) == len(ids)


def test_answers_are_valid_options(data):
    for unit, samples in data.items():
        for s in samples:
            opts = BENCH.options(s)
            assert len(opts) >= 2, s.id
            assert s.answer in opts, (s.id, s.answer, opts)


@pytest.mark.parametrize("modality", MODALITIES)
def test_prompts_all_samples(data, modality):
    for unit, samples in data.items():
        for s in samples:
            p = BENCH.prompt(s, modality, {"text_stride": 1})
            assert p.text.strip(), s.id
            if modality == "text":
                assert "<ts><ts/>" not in p.text, s.id        # 값으로 모두 바뀌어야 한다
            elif unit != "perception":
                assert "<ts><ts/>" not in p.text, s.id
            schema = p.response_schema()
            assert set(schema["required"]) <= {"reasoning", "answer"}


def test_official_prompt_wording(data):
    s = data["reasoning/causal"][0]
    v = BENCH.prompt(s, "vision", {}).text
    assert v.startswith("The time series in the image correspond to: " + ", ".join(s.raw["name_of_series"]) + ".\n\n")
    assert "\n\nSelect from the options below:" in v and v.endswith("\nOutput your reasoning and answer in JSON format.")
    tv = BENCH.prompt(s, "text+vision", {"text_stride": 1}).text
    assert tv.startswith("You are provided with time series data in BOTH text format and visual format (image).")
    assert "**Text Representation:**" in tv and "**Question:**" in tv and "**Options:**" in tv

    # perception: 이름이 없어 접두 문장이 붙지 않는다 (공식 코드와 같다)
    p = data["perception"][0]
    assert BENCH.prompt(p, "vision", {}).text.startswith(p.question)
    # text 조건: 값이 질문 속 placeholder 자리에 들어간다
    t = BENCH.prompt(p, "text", {"text_stride": 1}).text
    first = ",".join(f"{x:.2f}" for x in p.raw["timeseries"][0][:5])
    assert first in t

    a = data["reasoning/abductive"][0]
    for m in MODALITIES:
        assert BENCH.prompt(a, m, {"text_stride": 1}).text.startswith("You are an expert in basketball game analysis.")


def test_ts_placeholder_option(data):
    # 공식 vision 코드는 perception 질문 속 "<ts><ts/>" 를 그대로 보낸다. 기본값은 이를 따르고, 옵션으로 바꿀 수 있다
    p = data["perception"][0]
    for m in ("vision", "text+vision"):
        assert "<ts><ts/>" in BENCH.prompt(p, m, {"text_stride": 1}).text
        cleaned = BENCH.prompt(p, m, {"text_stride": 1, "ts_placeholder": "[see image]"}).text
        assert "<ts><ts/>" not in cleaned and "[see image]" in cleaned


def test_text_stride(data):
    s = data["reasoning/causal"][0]
    full = BENCH.prompt(s, "text", {"text_stride": 1}).text
    quarter = BENCH.prompt(s, "text", {"text_stride": 4}).text
    assert len(quarter) < len(full)


def test_time_axis_series_filtered(data):
    # 공식 코드: temporal 의 "Time Stamps", etiological 의 "Time" 은 chart 에 그리지 않는다
    for unit, name in (("reasoning/temporal_relation", "time stamps"), ("reasoning/etiological", "time")):
        hit = 0
        for s in data[unit]:
            raw_names = [str(n).strip().lower() for n in s.raw.get("name_of_series") or []]
            if name in raw_names and len(raw_names) > 1:
                hit += 1
                assert name not in [x.name.strip().lower() for x in s.series], s.id
                assert s.x is not None
        assert hit > 0, unit


def _subset(data, per_unit=3):
    out = []
    for unit, samples in data.items():
        # 앞, 중간, 끝 + series 수가 가장 많은 문항
        picks = {0, len(samples) // 2, len(samples) - 1}
        picks.add(max(range(len(samples)), key=lambda i: len(samples[i].series)))
        out += [samples[i] for i in sorted(picks)][: per_unit + 1]
    return out


def test_all_charts_on_every_task(data):
    for s in _subset(data):
        for spec in ALL_CHARTS:
            images = charts.render(s, spec.use, spec.params, spec.post)
            assert images, (s.id, spec.label)
            for im in images:
                w, h = im.size
                assert w > 50 and h > 50 and len(im.data) > 500, (s.id, spec.label)
                assert im.mime in ("image/jpeg", "image/png")
    assert charts.render(data["perception"][0], "none") is None


def test_chart_is_deterministic(data):
    s = data["perception"][3]
    a = charts.render(s, "tsrbench_baseline")[0]
    b = charts.render(s, "tsrbench_baseline")[0]
    assert a.sha == b.sha


def test_multi_view_returns_captioned_images(data):
    images = charts.render(data["perception"][0], "multi_view", {"views": ["full", "smooth", "diff"]})
    assert len(images) == 3 and all(im.caption for im in images)


def test_baseline_matches_team_examples():
    """augmentation_examples/*/baseline.png (팀에서 공식 설정으로 그린 그림)과 크기, 내용이 같은지."""
    np = pytest.importorskip("numpy")
    from PIL import Image

    from ts2img import preview

    for s in preview.example_samples():
        im = charts.render(s, "tsrbench_baseline")[0].pil().convert("RGB")
        ref = Image.open(preview.EXAMPLES_DIR / s.task / "baseline.png").convert("RGB")
        assert im.size == ref.size, s.task
        diff = np.abs(np.asarray(im, float) - np.asarray(ref, float)).mean()
        assert diff < 4.0, (s.task, diff)   # JPEG 압축 차이만 허용


@pytest.mark.skipif(not os.environ.get("TS2IMG_FULL"), reason="TS2IMG_FULL=1 일 때만 (수 분 소요)")
def test_baseline_chart_all_samples(data):
    for unit, samples in data.items():
        for s in samples:
            images = charts.render(s, "tsrbench_baseline")
            assert images and images[0].size[0] > 50, s.id
