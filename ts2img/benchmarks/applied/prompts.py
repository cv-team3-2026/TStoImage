"""text 와 vision 이 같은 질문, 같은 JSON schema 를 쓴다.

perception 의 text / vision 과 같이 reasoning 과 answer 를 둘 다 요구한다.
answer 만 요구하면 풀이를 쓰지 않아, 차트 유무와 풀이 유무가 섞인다.
"""
from __future__ import annotations

from ts2img.benchmarks.applied.windows import DAY, HISTORY
from ts2img.benchmarks.base import PromptSpec, Sample

LABELS = ["A", "B", "C", "D", "E"]


def _fmt(v: float) -> str:
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:.2f}"


def question_text(quantity: str, unit: str, start, ref: float, scale: float, lo: float, hi: float) -> str:
    from datetime import timedelta

    last = HISTORY - 1
    ref_from = HISTORY - DAY
    end = start + timedelta(hours=last)
    return (
        f"The past {HISTORY} hours of {quantity} are provided, one value per hour. "
        f"Index 0 is {start:%Y-%m-%d %H:%M} local time and index {last} is {end:%Y-%m-%d %H:%M}. "
        f"The mean of index {ref_from} through {last} is {ref:.1f} {unit}.\n\n"
        f"Day-to-day changes inside these {HISTORY // DAY} days have a typical size of {scale * 100:.1f}%. "
        f"Classify the mean of the next 24 hours, which are not provided, "
        f"relative to {ref:.1f} {unit}. "
        f"change = (next 24-hour mean - {ref:.1f}) / {ref:.1f} * 100.\n\n"
        f"A. much lower: change < -{hi:.1f}%\n"
        f"B. lower: -{hi:.1f}% <= change < -{lo:.1f}%\n"
        f"C. similar: -{lo:.1f}% <= change <= {lo:.1f}%\n"
        f"D. higher: {lo:.1f}% < change <= {hi:.1f}%\n"
        f"E. much higher: change > {hi:.1f}%"
    )


def build(sample: Sample, modality: str) -> PromptSpec:
    question = sample.question.strip()
    values = ", ".join(_fmt(v) for v in sample.series[0].values)
    last = HISTORY - 1
    tail = "Output your reasoning and answer in JSON format."
    values_line = f"The {HISTORY} hourly values from index 0 to {last} are:\n{values}"
    chart_line = (
        f"The image is a line chart of those {HISTORY} hourly values. "
        "The horizontal axis is the index, with 0 at the left. "
        "The next 24 hours are not shown."
    )
    if modality == "text":
        text = f"{question}\n\n{values_line}\n\n{tail}"
    elif modality == "vision":
        text = f"{question}\n\n{chart_line}\n\n{tail}"
    elif modality == "text+vision":
        text = (
            f"{question}\n\n{values_line}\n\n"
            f"The image is a line chart of the same {HISTORY} values. "
            "The horizontal axis is the index, with 0 at the left. "
            "The next 24 hours are not shown.\n\n"
            f"{tail}"
        )
    else:
        raise ValueError(f"모르는 modality: {modality}")
    return PromptSpec(text, "next_day_level", ("reasoning", "answer"))
