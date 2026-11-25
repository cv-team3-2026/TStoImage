"""실제 시계열 문항: 경계, 층화 추출, prompt 가 미래를 노출하지 않는지."""
from datetime import datetime, timedelta

import pytest

from ts2img.benchmarks.applied import parse, prompts
from ts2img.benchmarks.applied.adapter import AppliedKpx, _sample, kpx_missing_message
from ts2img.benchmarks.applied.windows import (
    HISTORY,
    HISTORY_DAYS,
    TARGET_N,
    build_windows,
    classify,
    select_windows,
    thresholds,
)
from ts2img.benchmarks.base import MODALITIES
from ts2img import charts
from ts2img.benchmarks import get_benchmark
from ts2img.config import expand, load_experiment, load_models
from ts2img.paths import EXPERIMENTS


def _hourly(start: datetime, values: list[float]):
    times = [start + timedelta(hours=i) for i in range(len(values))]
    return times, values


def _flat_then(future: float, days: int | None = None, level: float = 100.0):
    """앞 4주는 level, 마지막 날은 future. 목표일은 start+28일."""
    if days is None:
        days = HISTORY_DAYS + 1
    values = [level] * ((days - 1) * 24) + [future] * 24
    start = datetime(2020, 1, 1)
    return _hourly(start, values)


def test_classify_matches_prompt_boundaries():
    lo, hi = thresholds(0.02)  # floor: 1.0%, 3.0%
    assert (lo, hi) == (1.0, 3.0)
    assert classify(0, lo, hi) == "C"
    assert classify(2, lo, hi) == "D"
    assert classify(4, lo, hi) == "E"
    assert classify(-1.5, lo, hi) == "B"
    assert classify(-10, lo, hi) == "A"
    assert classify(lo, lo, hi) == "C"
    assert classify(hi, lo, hi) == "D"
    assert classify(-hi, lo, hi) == "B"


def test_flat_week_labels_and_naive():
    times, values = _flat_then(100)
    windows = build_windows(times, values)
    assert len(windows) == 1
    w = windows[0]
    assert w.answer == "C"
    assert w.naive_week == "C"
    assert w.target_date.isoformat() == "2020-01-29"
    assert len(w.history) == HISTORY

    times, values = _flat_then(104)  # +4% > 3%
    assert build_windows(times, values)[0].answer == "E"
    times, values = _flat_then(90)
    assert build_windows(times, values)[0].answer == "A"


def test_naive_week_uses_last_same_weekday_not_window_start():
    """4주 전 같은 요일이 달라도, 기준은 7일 전 같은 요일이다."""
    days = HISTORY_DAYS + 1
    values = [100.0] * (days * 24)
    values[0:24] = [200.0] * 24
    times, values = _hourly(datetime(2020, 1, 1), values)
    w = build_windows(times, values)[0]
    assert w.answer == "C"
    assert w.naive_week == "C"


def test_gap_day_is_not_a_window():
    start = datetime(2020, 1, 1)
    values = [10.0] * ((HISTORY_DAYS + 1) * 24)
    times = [start + timedelta(hours=i) for i in range(len(values))]
    del times[10]
    del values[10]
    assert build_windows(times, values) == []


def test_zero_reference_day_is_dropped():
    times, values = _flat_then(50, level=0.0)
    assert build_windows(times, values) == []


def test_stratified_sample_covers_months_and_keeps_gap():
    start = datetime(2020, 1, 1)
    # 400일, 약한 요일 패턴. 결측 없음.
    values = [100.0 + (i % 168) for i in range(400 * 24)]
    times, values = _hourly(start, values)
    windows = build_windows(times, values)
    picked, gap = select_windows(windows, TARGET_N, seed=0)
    assert len(picked) == TARGET_N
    assert gap == 2
    dates = [w.target_date for w in picked]
    assert dates == sorted(dates)
    assert all(abs((a - b).days) >= 2 for a, b in zip(dates, dates[1:]))
    months = {d.month for d in dates}
    assert months == set(range(1, 13))
    assert any(d.weekday() >= 5 for d in dates) and any(d.weekday() < 5 for d in dates)
    again, _ = select_windows(windows, TARGET_N, seed=0)
    assert [w.target_date for w in again] == dates


def test_prompt_hides_future_and_shares_schema():
    times, values = _flat_then(140)  # +40%, future mean 140 은 기준 100 과 다름
    w = build_windows(times, values)[0]
    spec = {"quantity": "hourly demand", "unit": "MW", "series": "Demand"}
    sample = _sample("kpx", 0, w, spec, gap=2)
    assert sample.answer == "E"
    assert "140" not in sample.question
    text = prompts.build(sample, "text")
    vision = prompts.build(sample, "vision")
    both = prompts.build(sample, "text+vision")
    assert text.schema_required == vision.schema_required == both.schema_required == ("reasoning", "answer")
    series = ", ".join(prompts._fmt(v) for v in sample.series[0].values)
    assert series in text.text
    assert series not in vision.text
    assert "140" not in vision.text
    assert sample.question.strip() in text.text
    assert sample.question.strip() in vision.text
    assert len(sample.series[0].values) == HISTORY
    images = charts.render(sample, "tsrbench_baseline")
    assert len(images) == 1 and images[0].data


def test_parsers_and_kpx_wide(tmp_path):
    metro = tmp_path / "metro.csv"
    metro.write_text(
        "date_time,traffic_volume\n"
        "2012-10-02 09:00:00,100\n"
        "2012-10-02 09:00:00,300\n"
        "2012-10-02 10:00:00,10\n",
        encoding="utf-8",
    )
    times, values = parse.parse_metro(metro)
    assert times == [datetime(2012, 10, 2, 9), datetime(2012, 10, 2, 10)]
    assert values == [200.0, 10.0]

    seoul = tmp_path / "seoul.csv"
    seoul.write_text(
        "Date,Rented Bike Count,Hour,Temperature(C)\n"
        "01/12/2017,5,0,1\n"
        "01/12/2017,7,1,1\n",
        encoding="utf-8",
    )
    times, values = parse.parse_seoul(seoul)
    assert times[0] == datetime(2017, 12, 1, 0)
    assert values == [5.0, 7.0]

    wide = tmp_path / "hourly.csv"
    hours = ",".join(f"{h}시" for h in range(1, 25))
    nums = ",".join(str(h * 10) for h in range(1, 25))
    wide.write_text(f"날짜,{hours}\n2024-01-01,{nums}\n", encoding="utf-8")
    times, values = parse.parse_kpx(wide)
    assert times[0] == datetime(2024, 1, 1, 0)
    assert times[-1] == datetime(2024, 1, 1, 23)
    assert values[0] == 10.0 and values[23] == 240.0

    quarter = tmp_path / "q.csv"
    quarter.write_text(
        "timestamp,load_mw\n"
        "2024-01-01 00:00,10\n"
        "2024-01-01 00:15,30\n"
        "2024-01-01 01:00,5\n",
        encoding="utf-8",
    )
    times, values = parse.parse_kpx(quarter)
    assert values[0] == 20.0 and values[1] == 5.0


def test_kpx_missing_message_points_at_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TS2IMG_DATA_DIR", str(tmp_path))
    bench = AppliedKpx()
    assert not bench.has_data("kpx")
    with pytest.raises(FileNotFoundError) as exc:
        bench.ensure_data(["kpx"])
    assert "hourly.csv" in str(exc.value)
    assert "data.go.kr/data/15065266" in kpx_missing_message(bench.csv_path())


def test_experiment_yaml_splits_datasets():
    exp = load_experiment(EXPERIMENTS / "applied_forecast.yaml")
    cells = expand(exp, load_models())
    keys = {(c.benchmark, c.modality, c.chart.use) for c in cells}
    assert keys == {
        ("applied_metro", "text", "none"),
        ("applied_metro", "vision", "tsrbench_baseline"),
        ("applied_seoul", "text", "none"),
        ("applied_seoul", "vision", "tsrbench_baseline"),
        ("applied_kpx", "text", "none"),
        ("applied_kpx", "vision", "tsrbench_baseline"),
    }
    assert exp.sampling_params() == {}
    for name in ("applied_metro", "applied_seoul", "applied_kpx"):
        bench = get_benchmark(name)
        assert bench.version == 2
        assert bench.revision == "next-day-level-v2"


def test_modalities_cover_prompt_builder():
    times, values = _flat_then(100)
    w = build_windows(times, values)[0]
    sample = _sample("metro", 0, w, {"quantity": "q", "unit": "u", "series": "S"}, 2)
    for modality in MODALITIES:
        assert prompts.build(sample, modality).text.strip()
