"""Seoul lookback 길이 ablation: text/vision 토큰 비교용 문항."""
from ts2img.benchmarks import get_benchmark
from ts2img.benchmarks.applied.context import build_prompt, with_tail
from ts2img import charts
from ts2img.config import expand, load_experiment, load_models
from ts2img.paths import EXPERIMENTS


def test_tail_keeps_answer_and_shortens_series():
    full = get_benchmark("applied_seoul").load("seoul_bike")[0]
    short = with_tail(full, 7 * 24, "hourly city-wide public bike rentals", "bikes")
    assert short.answer == full.answer
    assert len(short.series[0].values) == 168
    assert len(full.series[0].values) == 672
    assert short.raw["target_date"] == full.raw["target_date"]
    assert "168 hours" in short.question
    assert short.x is not None and len(short.x) == 168


def test_context_prompt_uses_series_length():
    full = get_benchmark("applied_seoul").load("seoul_bike")[0]
    short = with_tail(full, 14 * 24, "hourly city-wide public bike rentals", "bikes")
    text = build_prompt(short, "text").text
    vision = build_prompt(short, "vision").text
    assert "336 hourly values" in text
    assert "336 hourly values" in vision
    assert str(int(short.series[0].values[0])) in text or f"{short.series[0].values[0]:.2f}" in text


def test_context_benchmarks_and_experiment():
    for name, hours in (("applied_seoul_ctx7", 168), ("applied_seoul_ctx14", 336), ("applied_seoul_ctx28", 672)):
        s = get_benchmark(name).load("seoul_bike")[0]
        assert len(s.series[0].values) == hours
        imgs = charts.render(s, "line_style", {"scale": 3})
        assert imgs and imgs[0].data
    cells = expand(load_experiment(EXPERIMENTS / "applied_seoul_context.yaml"), load_models())
    assert len(cells) == 6  # 3 lookbacks × text/vision
    assert {c.modality for c in cells} == {"text", "vision"}
    assert {c.benchmark for c in cells} == {
        "applied_seoul_ctx7",
        "applied_seoul_ctx14",
        "applied_seoul_ctx28",
    }
