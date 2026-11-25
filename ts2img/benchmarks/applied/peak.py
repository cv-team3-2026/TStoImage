"""내일 95% 피크 시간. 정답은 그날 최대의 95% 이상인 시각들의 집합이다.

채점은 예측 집합과 정답 집합의 F1. 보여주는 값은 목표일 직전 4주, 672시간이다.
같은 요일이 네 번 들어 있다.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

from ts2img.benchmarks.applied.windows import SEED, select_windows
from ts2img.benchmarks.base import PromptSpec, Sample, Score, Series

HISTORY_DAYS = 28
DAY = 24
TARGET_N = 90
PEAK_FRAC = 0.95
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_HOUR = re.compile(r"\b([01]?\d|2[0-3])\b")
_ANSWER_HOUR = re.compile(r"""["']answer["']\s*:\s*["']?\s*([01]?\d|2[0-3])\b""")


class HourPrompt(PromptSpec):
    def response_schema(self) -> dict:
        schema = super().response_schema()
        schema["properties"]["answer"] = {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Hours, 0 through 23, that reach at least 95% of that day's highest volume",
        }
        return schema


def hour_distance(a: int, b: int) -> int:
    diff = abs(a - b) % 24
    return min(diff, 24 - diff)


def within_one_hour(a: int, b: int) -> bool:
    return hour_distance(a, b) <= 1


def _as_hour(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value == int(value):
        hour = int(value)
        return hour if 0 <= hour <= 23 else None
    text = str(value).strip()
    matched = re.fullmatch(r"([01]?\d|2[0-3])(?::00(?::00)?)?", text)
    if not matched:
        return None
    return int(matched.group(1))


def parse_hour(response: str | None) -> tuple[str | None, str | None]:
    if not response or not response.strip():
        return None, None
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict) and "answer" in obj:
        hour = _as_hour(obj["answer"])
        return (str(hour), "json") if hour is not None else (None, None)
    found = _ANSWER_HOUR.findall(text)
    if found:
        return str(int(found[-1])), "fallback"
    return None, None


def score_hour(label: str, response: str | None) -> Score:
    pred, parse = parse_hour(response)
    correct = pred is not None and within_one_hour(int(pred), int(label))
    return Score(pred=pred, correct=correct, parse=parse)


def _peak_hour(values: list[float]) -> int:
    return max(range(len(values)), key=lambda i: values[i])


def peak_hours(values: list[float], frac: float = PEAK_FRAC) -> list[int]:
    mx = max(values)
    return [i for i, v in enumerate(values) if v >= frac * mx]


def format_hours(hours) -> str:
    return ",".join(str(h) for h in sorted(set(hours)))


def set_f1(pred: set[int], gold: set[int]) -> float:
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    hit = len(pred & gold)
    if hit == 0:
        return 0.0
    precision = hit / len(pred)
    recall = hit / len(gold)
    return 2 * precision * recall / (precision + recall)


def _hours_from(value) -> list[int] | None:
    if isinstance(value, list):
        hours = []
        for item in value:
            hour = _as_hour(item)
            if hour is None:
                return None
            hours.append(hour)
        return sorted(set(hours))
    if isinstance(value, str):
        found = _HOUR.findall(value)
        return sorted({int(h) for h in found}) if found else None
    hour = _as_hour(value)
    return [hour] if hour is not None else None


def parse_hours(response: str | None) -> tuple[str | None, str | None]:
    if not response or not response.strip():
        return None, None
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict) and "answer" in obj:
        hours = _hours_from(obj["answer"])
        return (format_hours(hours), "json") if hours is not None else (None, None)
    listed = re.search(r"""["']answer["']\s*:\s*\[([^\]]*)\]""", text)
    if listed:
        hours = _hours_from(listed.group(1))
        return (format_hours(hours), "fallback") if hours is not None else (None, None)
    found = _ANSWER_HOUR.findall(text)
    if found:
        return str(int(found[-1])), "fallback"
    return None, None


def score_hours(label: str, response: str | None) -> Score:
    pred, parse = parse_hours(response)
    if pred is None:
        return Score(pred=None, correct=False, parse=None, f1=0.0)
    gold = {int(h) for h in label.split(",") if h != ""}
    got = {int(h) for h in pred.split(",") if h != ""}
    value = set_f1(got, gold)
    return Score(pred=pred, correct=value == 1.0, parse=parse, f1=value)


def question_text(start: datetime, end: datetime, target) -> str:
    from ts2img.charts.clock_days import WEEKS_SHOWN

    weekday = WEEKDAYS[target.weekday()]
    shown_start = start + timedelta(days=max(0, HISTORY_DAYS - WEEKS_SHOWN * 7))
    return (
        f"The chart shows hourly interstate traffic volume from {shown_start:%Y-%m-%d %H:%M} "
        f"through {end:%Y-%m-%d %H:%M} local time. "
        f"The figure shows {WEEKS_SHOWN} weekly charts side by side, oldest week on the left. "
        f"Each chart is one week. "
        f"All charts use the same vertical scale. Hour 0 is midnight.\n\n"
        f"Predict all hours, from 0 through 23, at which traffic on {target.isoformat()} ({weekday}) "
        f"will be at least 95% of that day's highest volume. "
        f"Output every such hour as an array, for example [7, 16]."
    )


def _lookup(times, values) -> dict[datetime, float]:
    acc: dict[datetime, list[float]] = defaultdict(list)
    for t, v in zip(times, values):
        acc[t.replace(minute=0, second=0, microsecond=0)].append(v)
    return {t: sum(vs) / len(vs) for t, vs in acc.items()}


def build_samples(times, values, n: int = TARGET_N, seed: int = SEED) -> tuple[list[Sample], int]:
    lookup = _lookup(times, values)
    windows = []
    for day in sorted({t.date() for t in lookup}):
        origin = datetime(day.year, day.month, day.day) - timedelta(days=HISTORY_DAYS)
        hist = []
        xs = []
        ok = True
        for i in range(HISTORY_DAYS * DAY):
            t = origin + timedelta(hours=i)
            if t not in lookup:
                ok = False
                break
            hist.append(lookup[t])
            xs.append(t)
        if not ok:
            continue
        future = []
        for i in range(DAY):
            t = datetime(day.year, day.month, day.day) + timedelta(hours=i)
            if t not in lookup:
                ok = False
                break
            future.append(lookup[t])
        if not ok:
            continue
        answer = format_hours(peak_hours(future))
        week_at = (HISTORY_DAYS - 7) * DAY
        week = format_hours(peak_hours(hist[week_at : week_at + DAY]))
        yesterday = format_hours(peak_hours(hist[-DAY:]))
        windows.append((day, origin, xs, hist, answer, week, yesterday))

    class _W:
        def __init__(self, day, origin):
            self.target_date = day
            self.start = origin

    picked, gap = select_windows([_W(w[0], w[1]) for w in windows], n, seed)
    chosen = {w.target_date for w in picked}
    samples = []
    for day, origin, xs, hist, answer, week, yesterday in windows:
        if day not in chosen:
            continue
        end = origin + timedelta(hours=len(hist) - 1)
        samples.append(
            Sample(
                id=f"metro#{day.isoformat()}",
                unit="metro",
                task="metro",
                idx=0,
                question=question_text(origin, end, day),
                answer=answer,
                series=[Series("Traffic volume", hist)],
                choices=[str(h) for h in range(24)],
                x=xs,
                raw={
                    "target_date": day.isoformat(),
                    "naive_hours_week": week,
                    "naive_hours_yesterday": yesterday,
                    "min_gap_days": gap,
                    "seed": seed,
                },
            )
        )
    samples.sort(key=lambda s: s.raw["target_date"])
    for i, s in enumerate(samples):
        s.idx = i
    return samples, gap


def vision_prompt(sample: Sample) -> HourPrompt:
    text = (
        f"{sample.question.strip()}\n\n"
        "The horizontal axis is local time.\n\n"
        "Output your reasoning and answer in JSON format."
    )
    return HourPrompt(text, "peak_hour", ("reasoning", "answer"))
