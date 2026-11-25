"""따릉이 재배치 피크 시각 문항."""
from datetime import datetime, timedelta

from ts2img import charts
from ts2img.benchmarks import get_benchmark
from ts2img.benchmarks.applied.seoul_peak import (
    HISTORY,
    HORIZON,
    THRESHOLD,
    build_prompt,
    build_samples,
    peak_hours_above,
    score_seoul_hours,
    text_tables,
)
from ts2img.config import expand, load_experiment, load_models
from ts2img.paths import EXPERIMENTS


def test_peak_hours_above_threshold():
    assert peak_hours_above([10, 1000, 999, 1500], 1000) == [1, 3]
    assert peak_hours_above([0] * 24, 1000) == []


def test_score_accepts_peak_hours_key():
    score = score_seoul_hours("8,17", '{"peak_hours": [8, 17]}')
    assert score.pred == "8,17" and score.f1 == 1.0 and score.parse == "json"
    score2 = score_seoul_hours("8,17", '{"reasoning": "x", "answer": [8]}')
    assert score2.pred == "8" and abs(score2.f1 - 2 / 3) < 1e-9


def test_build_hides_target_rentals_and_keeps_forecast_weather():
    start = datetime(2018, 6, 4)  # Monday
    times, rent, temp, rain, hol, func = [], [], [], [], [], []
    for i in range(40 * 24):
        t = start + timedelta(hours=i)
        times.append(t)
        # 평일 출퇴근, 비 오면 붕괴
        base = 1200 if t.hour in (8, 9, 17, 18, 19) else 200
        raining = t.day % 5 == 0
        rent.append(50 if raining else base)
        temp.append(20.0 + (5 if t.month == 6 else 0))
        rain.append(3.0 if raining else 0.0)
        hol.append(0.0)
        func.append(1.0)
    samples, gap, stats = build_samples(times, rent, temp, rain, hol, func, n=12, seed=0)
    assert samples and stats["n"] == 12
    s = samples[0]
    assert len(s.series[0].values) == HISTORY
    assert len(s.series[1].values) == HISTORY + HORIZON
    assert len(s.series[2].values) == HISTORY + HORIZON
    assert s.split_index == HISTORY
    assert s.raw["threshold"] == THRESHOLD
    assert s.raw["target_date"] not in "".join(str(t) for t in s.x)
    images = charts.render(s, "bike_peak", {"scale": 3})
    assert len(images) == 1 and images[0].data
    w, h = images[0].size
    assert w > h  # 가로 배치


def test_seoul_peak_experiment_is_vision_scale3():
    exp = load_experiment(EXPERIMENTS / "applied_seoul_peak_scale3.yaml")
    cells = expand(exp, load_models())
    assert {(c.benchmark, c.modality, c.chart.use, c.chart.params.get("scale")) for c in cells} == {
        ("applied_seoul_peak", "vision", "bike_peak", 3)
    }
    assert get_benchmark("applied_seoul_peak").revision == "seoul-peak-v1"


def test_seoul_peak_gemini_matches_scale3_chart():
    exp = load_experiment(EXPERIMENTS / "applied_seoul_peak_gemini.yaml")
    cells = expand(exp, load_models())
    assert len(cells) == 1
    c = cells[0]
    assert c.benchmark == "applied_seoul_peak"
    assert c.modality == "vision"
    assert c.chart.use == "bike_peak" and c.chart.params.get("scale") == 3
    assert c.model.key == "gemini-hydrogen"
    assert c.model.model == "gemini-4-hydrogen"


def test_seoul_peak_text_prompt_has_numbers_not_chart():
    start = datetime(2018, 6, 4)
    times, rent, temp, rain, hol, func = [], [], [], [], [], []
    for i in range(20 * 24):
        t = start + timedelta(hours=i)
        times.append(t)
        rent.append(1200 if t.hour in (8, 17) else 100)
        temp.append(22.0)
        rain.append(0.0)
        hol.append(0.0)
        func.append(1.0)
    samples, _, _ = build_samples(times, rent, temp, rain, hol, func, n=3, seed=0)
    s = samples[0]
    prompt = build_prompt(s, "text")
    assert "1000" in prompt.text
    assert "Past 168 hourly bike rentals" in prompt.text
    assert str(int(s.series[0].values[0])) in text_tables(s)
    assert "left chart" not in prompt.text.lower()
    vision = build_prompt(s, "vision")
    assert "left chart" in vision.text.lower()


def test_seoul_peak_gemini_text_experiment():
    exp = load_experiment(EXPERIMENTS / "applied_seoul_peak_gemini_text.yaml")
    cells = expand(exp, load_models())
    assert len(cells) == 1
    assert cells[0].modality == "text" and cells[0].model.key == "gemini-hydrogen"
    assert cells[0].chart.use == "none"


def test_seoul_peak_text_vision_prompt():
    start = datetime(2018, 6, 4)
    times, rent, temp, rain, hol, func = [], [], [], [], [], []
    for i in range(20 * 24):
        t = start + timedelta(hours=i)
        times.append(t)
        rent.append(1200 if t.hour in (8, 17) else 100)
        temp.append(22.0)
        rain.append(0.0)
        hol.append(0.0)
        func.append(1.0)
    samples, _, _ = build_samples(times, rent, temp, rain, hol, func, n=3, seed=0)
    prompt = build_prompt(samples[0], "text+vision")
    assert "Past 168 hourly bike rentals" in prompt.text
    assert "image" in prompt.text.lower()


def test_lab_experiments_cover_three_modalities():
    peak = expand(load_experiment(EXPERIMENTS / "applied_seoul_peak_lab.yaml"), load_models())
    forecast = expand(load_experiment(EXPERIMENTS / "applied_seoul_forecast_lab.yaml"), load_models())
    assert {c.modality for c in peak} == {"text", "vision", "text+vision"}
    assert {c.modality for c in forecast} == {"text", "vision", "text+vision"}
    assert all(c.model.key == "qwen3-vl-4b" for c in peak + forecast)
    assert {c.chart.use for c in peak if c.modality != "text"} == {"bike_peak"}
    assert {c.chart.use for c in forecast if c.modality != "text"} == {"line_style"}
    assert all(c.benchmark == "applied_seoul" for c in forecast)


