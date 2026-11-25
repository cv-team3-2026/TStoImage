"""내일 피크 시각: ±1시간 채점, 미래 시각은 차트에 없다."""
from datetime import datetime, timedelta

from ts2img.benchmarks.applied.peak import (
    HISTORY_DAYS,
    build_samples,
    hour_distance,
    parse_hour,
    score_hour,
    score_hours,
    within_one_hour,
)
from ts2img import charts
from ts2img.benchmarks import get_benchmark
from ts2img.config import expand, load_experiment, load_models
from ts2img.paths import EXPERIMENTS


def test_hour_wraps_at_midnight():
    assert hour_distance(0, 23) == 1
    assert within_one_hour(0, 23)
    assert within_one_hour(16, 17)
    assert not within_one_hour(7, 16)


def test_score_accepts_json_hour_within_one():
    raw = '{"reasoning": "evening", "answer": "15"}'
    score = score_hour("16", raw)
    assert score.pred == "15" and score.correct and score.parse == "json"
    assert score_hour("7", raw).correct is False
    assert parse_hour("not json") == (None, None)


def test_score_hours_uses_set_f1():
    raw = '{"reasoning": "both rushes", "answer": [7, 16]}'
    score = score_hours("7,16", raw)
    assert score.pred == "7,16" and score.f1 == 1.0 and score.correct
    partial = score_hours("7,16", '{"answer": [16]}')
    assert partial.pred == "16" and abs(partial.f1 - 2 / 3) < 1e-9 and not partial.correct
    assert score_hours("7,16", "not json").pred is None and score_hours("7,16", "not json").f1 == 0.0


def test_peak_samples_hide_the_target_day(tmp_path):
    start = datetime(2020, 1, 6)  # Monday
    times, values = [], []
    for i in range(80 * 24):
        t = start + timedelta(hours=i)
        # 평일은 16시, 주말은 12시가 최대
        hour = t.hour
        values.append(1000 + (5000 if hour == (12 if t.weekday() >= 5 else 16) else hour))
        times.append(t)
    samples, gap = build_samples(times, values, n=10, seed=0)
    assert samples and gap == 2
    s = samples[0]
    assert len(s.series[0].values) == HISTORY_DAYS * 24
    assert s.x[-1] + timedelta(hours=1) == datetime.fromisoformat(s.raw["target_date"])
    assert s.raw["target_date"] not in "".join(str(t) for t in s.x)
    images = charts.render(s, "clock_days")
    assert len(images) == 1 and images[0].data


def test_peak_experiment_is_vision_only():
    exp = load_experiment(EXPERIMENTS / "applied_peak_hour.yaml")
    cells = expand(exp, load_models())
    assert {(c.benchmark, c.modality, c.chart.use) for c in cells} == {
        ("applied_metro_peak", "vision", "clock_days")
    }
    assert get_benchmark("applied_metro_peak").revision == "peak-hours-v4"
