"""서울 따릉이: 내일 재배치 긴급 피크 시각 집합.

과거 7일 대여량 + 내일 기상예보(기온·강수)를 보고, 시간당 대여량이 임계치 이상인
시각을 모두 맞춘다. 채점은 집합 F1. 단순 복붙이 깨지기 쉬운 날(강수·기온·휴일 전환)을 우선 뽑는다.
"""
from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from ts2img.benchmarks.applied.peak import WEEKDAYS, _hours_from, format_hours, score_hours, set_f1
from ts2img.benchmarks.base import PromptSpec, Sample, Score, Series

HISTORY_DAYS = 7
DAY = 24
HISTORY = HISTORY_DAYS * DAY
HORIZON = 24
TARGET_N = 60
SEED = 0
THRESHOLD = 1000.0
TEMP_SHIFT_C = 5.0


class SeoulPeakPrompt(PromptSpec):
    def response_schema(self) -> dict:
        schema = super().response_schema()
        schema["properties"]["answer"] = {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Hours 0-23 when rentals are expected to exceed the threshold",
        }
        return schema


def peak_hours_above(values: list[float], threshold: float = THRESHOLD) -> list[int]:
    return [i for i, v in enumerate(values) if v >= threshold]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _rained(xs: list[float]) -> bool:
    return any(v > 0 for v in xs)


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def regime_shift(
    target: date,
    fut_temp: list[float],
    fut_rain: list[float],
    fut_holiday: float,
    y_temp: list[float],
    y_rain: list[float],
    y_holiday: float,
    w_temp: list[float],
    w_rain: list[float],
    w_holiday: float,
) -> bool:
    """전일/전주 대비 강수·기온·평일↔주말·공휴일 전환."""
    yesterday = target - timedelta(days=1)
    if _rained(fut_rain) != _rained(y_rain) or _rained(fut_rain) != _rained(w_rain):
        return True
    if abs(_mean(fut_temp) - _mean(y_temp)) >= TEMP_SHIFT_C:
        return True
    if abs(_mean(fut_temp) - _mean(w_temp)) >= TEMP_SHIFT_C:
        return True
    if _is_weekend(target) != _is_weekend(yesterday):
        return True
    if (fut_holiday >= 0.5) != (y_holiday >= 0.5) or (fut_holiday >= 0.5) != (w_holiday >= 0.5):
        return True
    return False


def _lookup(times, *series_lists) -> dict[datetime, tuple]:
    acc: dict[datetime, list[tuple]] = defaultdict(list)
    for row in zip(times, *series_lists):
        t = row[0].replace(minute=0, second=0, microsecond=0)
        acc[t].append(row[1:])
    out = {}
    for t, rows in acc.items():
        cols = list(zip(*rows))
        out[t] = tuple(sum(c) / len(c) for c in cols)
    return out


def build_samples(
    times,
    rentals,
    temperature,
    rainfall,
    holiday,
    functioning,
    n: int = TARGET_N,
    seed: int = SEED,
    threshold: float = THRESHOLD,
) -> tuple[list[Sample], int, dict]:
    lookup = _lookup(times, rentals, temperature, rainfall, holiday, functioning)
    candidates = []
    for day in sorted({t.date() for t in lookup}):
        origin = datetime(day.year, day.month, day.day) - timedelta(days=HISTORY_DAYS)
        hist_r, hist_t, hist_rain = [], [], []
        fut_r, fut_t, fut_rain = [], [], []
        fut_hol, y_hol, w_hol = [], [], []
        y_t, y_rain, w_t, w_rain = [], [], [], []
        ok = True
        for i in range(HISTORY + HORIZON):
            t = origin + timedelta(hours=i)
            if t not in lookup:
                ok = False
                break
            r, temp, rain, hol, func = lookup[t]
            if i < HISTORY:
                hist_r.append(r)
                hist_t.append(temp)
                hist_rain.append(rain)
                # 7일 창의 첫날 = 목표일과 같은 요일(7일 전)
                if i < DAY:
                    w_t.append(temp)
                    w_rain.append(rain)
                    w_hol.append(hol)
                if i >= HISTORY - DAY:
                    y_t.append(temp)
                    y_rain.append(rain)
                    y_hol.append(hol)
            else:
                fut_r.append(r)
                fut_t.append(temp)
                fut_rain.append(rain)
                fut_hol.append(hol)
                if func < 0.5:
                    ok = False
                    break
        if not ok or len(w_t) != DAY:
            continue
        answer = format_hours(peak_hours_above(fut_r, threshold))
        week = format_hours(peak_hours_above(hist_r[:DAY], threshold))
        yesterday = format_hours(peak_hours_above(hist_r[-DAY:], threshold))
        shift = regime_shift(
            day,
            fut_t,
            fut_rain,
            _mean(fut_hol),
            y_t,
            y_rain,
            _mean(y_hol),
            w_t,
            w_rain,
            _mean(w_hol),
        )
        xs = [origin + timedelta(hours=i) for i in range(HISTORY)]
        candidates.append(
            {
                "day": day,
                "origin": origin,
                "xs": xs,
                "hist_r": hist_r,
                "temp_full": hist_t + fut_t,
                "rain_full": hist_rain + fut_rain,
                "answer": answer,
                "week": week,
                "yesterday": yesterday,
                "shift": shift,
                "fut_rain": sum(fut_rain),
            }
        )

    hard = [c for c in candidates if c["shift"]]
    easy = [c for c in candidates if not c["shift"]]
    rng = random.Random(seed)
    rng.shuffle(hard)
    rng.shuffle(easy)
    ordered = hard + easy

    picked = []
    used_gap = 0
    for gap in (2, 1, 0):
        used_gap = gap
        picked = []
        for c in ordered:
            if all(abs((c["day"] - p["day"]).days) >= gap for p in picked):
                picked.append(c)
            if len(picked) >= n:
                break
        if len(picked) >= n:
            break
    picked.sort(key=lambda c: c["day"])

    samples = []
    for i, c in enumerate(picked):
        day, origin = c["day"], c["origin"]
        end = origin + timedelta(hours=HISTORY - 1)
        samples.append(
            Sample(
                id=f"seoul_bike#{day.isoformat()}",
                unit="seoul_bike",
                task="seoul_bike",
                idx=i,
                question=question_text(origin, end, day, threshold),
                answer=c["answer"],
                series=[
                    Series("Bike rentals", list(c["hist_r"])),
                    Series("Temperature (C)", list(c["temp_full"])),
                    Series("Rainfall (mm)", list(c["rain_full"])),
                ],
                choices=[str(h) for h in range(24)],
                x=c["xs"],
                split_index=HISTORY,
                raw={
                    "target_date": day.isoformat(),
                    "threshold": threshold,
                    "history_hours": HISTORY,
                    "horizon_hours": HORIZON,
                    "naive_hours_week": c["week"],
                    "naive_hours_yesterday": c["yesterday"],
                    "regime_shift": c["shift"],
                    "target_rain_mm": c["fut_rain"],
                    "min_gap_days": used_gap,
                    "seed": seed,
                },
            )
        )
    stats = {
        "candidates": len(candidates),
        "hard": len(hard),
        "picked_hard": sum(1 for c in picked if c["shift"]),
        "n": len(samples),
        "gap": used_gap,
    }
    return samples, used_gap, stats


def question_text(start: datetime, end: datetime, target: date, threshold: float) -> str:
    weekday = WEEKDAYS[target.weekday()]
    return (
        f"The left chart shows hourly Seoul public bike rentals from {start:%Y-%m-%d %H:%M} "
        f"through {end:%Y-%m-%d %H:%M} local time. "
        f"The red dashed line is the relocation-peak threshold of {threshold:.0f} bikes per hour. "
        f"The grey band on the right of that chart is the next day "
        f"({target.isoformat()}, {weekday}); rentals there are not drawn.\n\n"
        f"The right chart shows temperature (line) and rainfall (bars) for the same past week "
        f"plus the weather forecast for that next day (same grey band).\n\n"
        f"Predict every hour from 0 through 23 on {target.isoformat()} when rentals will be "
        f"at or above {threshold:.0f}. Output every such hour as an array, for example [8, 9, 17, 18]. "
        f"If none, output []."
    )


def vision_prompt(sample: Sample) -> SeoulPeakPrompt:
    text = (
        f"{sample.question.strip()}\n\n"
        "Both charts share the same time axis. Hour 0 is midnight.\n\n"
        "Output your reasoning and answer in JSON format."
    )
    return SeoulPeakPrompt(text, "seoul_peak_hours", ("reasoning", "answer"))


def _fmt_num(v: float) -> str:
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:.2f}"


def text_tables(sample: Sample) -> str:
    """과거 168시간 대여량과, 과거+예보 기온·강수를 표로 적는다."""
    hist = int(sample.raw.get("history_hours", HISTORY))
    horizon = int(sample.raw.get("horizon_hours", HORIZON))
    rentals = sample.series[0].values
    temp = sample.series[1].values
    rain = sample.series[2].values
    start = sample.x[0] if sample.x else None
    lines = [
        f"Past {hist} hourly bike rentals (index 0 = {start:%Y-%m-%d %H:%M} local time, one value per hour):",
        ", ".join(_fmt_num(v) for v in rentals),
        "",
        f"Temperature (C) for the same {hist} hours plus the next {horizon}-hour forecast "
        f"(indices {hist}..{hist + horizon - 1} are the forecast day):",
        ", ".join(_fmt_num(v) for v in temp),
        "",
        f"Rainfall (mm) on the same {hist + horizon} hourly indices:",
        ", ".join(_fmt_num(v) for v in rain),
    ]
    return "\n".join(lines)


def text_question(sample: Sample) -> str:
    thr = float(sample.raw["threshold"])
    target = sample.raw["target_date"]
    day = date.fromisoformat(target)
    weekday = WEEKDAYS[day.weekday()]
    start, end = sample.x[0], sample.x[-1]
    return (
        f"Hourly Seoul public bike rentals from {start:%Y-%m-%d %H:%M} through {end:%Y-%m-%d %H:%M} "
        f"local time are given as numbers below, together with temperature and rainfall for that week "
        f"and the weather forecast for {target} ({weekday}). "
        f"Rentals for {target} are not provided.\n\n"
        f"Predict every hour from 0 through 23 on {target} when rentals will be "
        f"at or above {thr:.0f}. Output every such hour as an array, for example [8, 9, 17, 18]. "
        f"If none, output []. Hour 0 is midnight."
    )


def text_prompt(sample: Sample) -> SeoulPeakPrompt:
    text = (
        f"{text_question(sample)}\n\n"
        f"{text_tables(sample)}\n\n"
        "Output your reasoning and answer in JSON format."
    )
    return SeoulPeakPrompt(text, "seoul_peak_hours", ("reasoning", "answer"))


def text_vision_prompt(sample: Sample) -> SeoulPeakPrompt:
    text = (
        f"{sample.question.strip()}\n\n"
        f"{text_tables(sample)}\n\n"
        "The image is the same data as charts: left = past rentals with the red threshold "
        "and a grey band for the forecast day (rentals not drawn there); "
        "right = temperature and rainfall including that day's forecast. "
        "Both charts share the same time axis. Hour 0 is midnight.\n\n"
        "Output your reasoning and answer in JSON format."
    )
    return SeoulPeakPrompt(text, "seoul_peak_hours", ("reasoning", "answer"))


def build_prompt(sample: Sample, modality: str) -> SeoulPeakPrompt:
    if modality == "vision":
        return vision_prompt(sample)
    if modality == "text":
        return text_prompt(sample)
    if modality == "text+vision":
        return text_vision_prompt(sample)
    raise ValueError(f"applied_seoul_peak 는 text / vision / text+vision 만 씁니다: {modality}")


def score_seoul_hours(label: str, response: str | None) -> Score:
    if response and response.strip():
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "peak_hours" in obj and "answer" not in obj:
            hours = _hours_from(obj["peak_hours"])
            if hours is not None:
                pred = format_hours(hours)
                gold = {int(h) for h in label.split(",") if h != ""}
                got = set(hours)
                value = set_f1(got, gold)
                return Score(pred=pred, correct=value == 1.0, parse="json", f1=value)
    return score_hours(label, response)


def naive_f1(samples: list[Sample], key: str) -> float:
    vals = []
    for s in samples:
        gold = {int(h) for h in s.answer.split(",") if h != ""}
        pred = {int(h) for h in str(s.raw.get(key, "")).split(",") if h != ""}
        vals.append(set_f1(pred, gold))
    return sum(vals) / len(vals) if vals else 0.0
