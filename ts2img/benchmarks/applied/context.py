"""lookback 길이를 줄인 Seoul 문항. text 대 vision 입력 토큰 비교용.

원본 applied_seoul 과 같은 90일·같은 정답이지만, 보여주는 이력만 끝에서 N시간이다.
정답·경계(lo/hi)·ref_mean 은 원래 4주 창 기준을 유지한다 (비교 가능하도록).
"""
from __future__ import annotations

from copy import copy
from datetime import timedelta

from ts2img.benchmarks.applied import prompts
from ts2img.benchmarks.base import Sample, Series


def _timeline(sample: Sample) -> list:
    """이력 시각축. sample.x 가 없으면 target_date 직전 구간으로 복원한다."""
    if sample.x:
        return list(sample.x)
    from datetime import datetime

    n = len(sample.series[0].values)
    day = datetime.fromisoformat(sample.raw["target_date"])
    end = day - timedelta(hours=1)
    start = end - timedelta(hours=n - 1)
    return [start + timedelta(hours=i) for i in range(n)]


def question_for_tail(sample: Sample, hours: int, quantity: str, unit: str, xs: list) -> str:
    raw = sample.raw
    start, end = xs[0], xs[-1]
    last = hours - 1
    ref_from = hours - 24
    return (
        f"The past {hours} hours of {quantity} are provided, one value per hour. "
        f"Index 0 is {start:%Y-%m-%d %H:%M} local time and index {last} is {end:%Y-%m-%d %H:%M}. "
        f"The mean of index {ref_from} through {last} is {raw['ref_mean']:.1f} {unit}.\n\n"
        f"Day-to-day changes inside these {hours // 24} days have a typical size of {raw['scale'] * 100:.1f}%. "
        f"Classify the mean of the next 24 hours, which are not provided, "
        f"relative to {raw['ref_mean']:.1f} {unit}. "
        f"change = (next 24-hour mean - {raw['ref_mean']:.1f}) / {raw['ref_mean']:.1f} * 100.\n\n"
        f"A. much lower: change < -{raw['hi']:.1f}%\n"
        f"B. lower: -{raw['hi']:.1f}% <= change < -{raw['lo']:.1f}%\n"
        f"C. similar: -{raw['lo']:.1f}% <= change <= {raw['lo']:.1f}%\n"
        f"D. higher: {raw['lo']:.1f}% < change <= {raw['hi']:.1f}%\n"
        f"E. much higher: change > {raw['hi']:.1f}%"
    )


def with_tail(sample: Sample, hours: int, quantity: str, unit: str) -> Sample:
    if hours > len(sample.series[0].values):
        raise ValueError(f"tail {hours}h > series {len(sample.series[0].values)}")
    xs = _timeline(sample)[-hours:]
    out = copy(sample)
    out.series = [Series(sample.series[0].name, list(sample.series[0].values[-hours:]))]
    out.x = xs
    out.question = question_for_tail(sample, hours, quantity, unit, xs)
    out.raw = dict(sample.raw)
    out.raw["tail_hours"] = hours
    out.raw["full_hours"] = len(sample.series[0].values)
    return out


def build_prompt(sample: Sample, modality: str) -> prompts.PromptSpec:
    """series 길이에 맞춰 숫자/차트 설명을 쓴다 (고정 672 가 아님)."""
    n = len(sample.series[0].values)
    values = ", ".join(prompts._fmt(v) for v in sample.series[0].values)
    last = n - 1
    # 입력 토큰·지연 비교가 목적이라 긴 chain-of-thought 를 막는다.
    tail = (
        'Reply with ONLY a short JSON object, answer field first: '
        '{"answer":"A|B|C|D|E","reasoning":"<one short sentence>"}.'
    )
    values_line = f"The {n} hourly values from index 0 to {last} are:\n{values}"
    chart_line = (
        f"The image is a line chart of those {n} hourly values. "
        "The horizontal axis is the index, with 0 at the left. "
        "The next 24 hours are not shown."
    )
    question = sample.question.strip()
    if modality == "text":
        text = f"{question}\n\n{values_line}\n\n{tail}"
    elif modality == "vision":
        text = f"{question}\n\n{chart_line}\n\n{tail}"
    elif modality == "text+vision":
        text = (
            f"{question}\n\n{values_line}\n\n"
            f"The image is a line chart of the same {n} values. "
            "The horizontal axis is the index, with 0 at the left. "
            "The next 24 hours are not shown.\n\n"
            f"{tail}"
        )
    else:
        raise ValueError(f"모르는 modality: {modality}")
    return prompts.PromptSpec(text, "next_day_level", ("reasoning", "answer"))
