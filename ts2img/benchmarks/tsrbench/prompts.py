"""TSRBench 공식 prompt 재현.

출처 (third_party/TSRBench/inference):
- vision:      vision_opensource/vision_inference_opensource.py
- text:        text_opensource/text_inference_opensource.py
- text+vision: multimodal_gpt/evaluate_gpt_multimodal.py
- abductive:   *_abductive.py (오픈소스용이 있으면 오픈소스용)
문구는 공식 코드 그대로 둔다. 공개 데이터와 맞지 않아 맞춘 부분은 CHANGES.md 참고.
"""
from __future__ import annotations

import re

from ts2img.benchmarks.base import PromptSpec, Sample

LABELS = ["A", "B", "C", "D", "E", "F", "G"]
TS_TOKEN = "<ts><ts/>"


def _choice_text(choices) -> str:
    text = "\n"
    if isinstance(choices, dict):
        for key in sorted(choices.keys()):
            text += f"{key}. {choices[key]}\n"
    elif isinstance(choices, list):
        text = "".join(f"{LABELS[i]}. {val}\n" for i, val in enumerate(choices))
    return text


def option_labels(sample: Sample) -> list[str]:
    c = sample.choices
    if isinstance(c, dict) and c:
        return sorted(c.keys())
    if isinstance(c, list) and c:
        return LABELS[: len(c)]
    # perception: 선택지가 질문 본문에 들어 있다
    found = re.findall(r"^([A-G])\. ", sample.question, flags=re.M)
    return found or ["A", "B", "C", "D"]


def _stride(values: list, stride, is_float: bool) -> list:
    if stride == "gpt_official":  # 공식 GPT용 text 스크립트: float 4개 중 1개, 그 외 6개 중 1개
        stride = 4 if is_float else 6
    return values[:: int(stride or 1)]


def _text_names(sample: Sample) -> list[str]:
    """text 조건용 series 이름. 이름이 없거나 모자라면 'Series N' 으로 채운다. (CHANGES.md)"""
    ts = sample.raw["timeseries"]
    names = list(sample.raw.get("name_of_series") or [])
    return [names[i] if i < len(names) else f"Series {i + 1}" for i in range(len(ts))]


# ---- 일반 task -------------------------------------------------------------
def _question_with_image(sample: Sample, opts: dict) -> str:
    """이미지를 넣는 조건의 질문. 공식 코드는 질문 속 "<ts><ts/>" 를 그대로 보낸다 (perception 700문항)."""
    repl = opts.get("ts_placeholder")
    if repl is None or repl == "keep":
        return sample.question
    return sample.question.replace(TS_TOKEN, str(repl))


def _vision(sample: Sample, opts: dict) -> PromptSpec:
    question = _question_with_image(sample, opts)
    names = sample.raw.get("name_of_series")
    if names:
        question = "The time series in the image correspond to: " + ", ".join(names) + ".\n\n" + question
    text = (
        question + "\n\nSelect from the options below:" + _choice_text(sample.choices)
        + "\nOutput your reasoning and answer in JSON format."
    )
    return PromptSpec(text, "chronological_order", ("reasoning", "answer"))


def _text(sample: Sample, opts: dict) -> PromptSpec:
    ts = sample.raw["timeseries"]
    question = sample.question
    if question.count(TS_TOKEN) != len(ts):
        # 공식: 질문 뒤에 series 마다 placeholder 를 붙인다
        question += " Here are the time series"
        for name in _text_names(sample):
            question += f" '{name}': {TS_TOKEN}. "
    question += (
        " Select from the options below:" + _choice_text(sample.choices)
        + "\nOutput your reasoning and answer in JSON format."
    )
    # 공식: 첫 series 의 첫 값이 float 인지로 전체 형식을 정한다
    is_float = isinstance(ts[0][0], float)
    parts = question.split(TS_TOKEN)
    prompt = parts[0]
    for i, values in enumerate(ts):
        vals = _stride(values, opts.get("text_stride", 1), is_float)
        cur = ",".join(f"{v:.2f}" for v in vals) if is_float else ",".join(f"{v}" for v in vals)
        prompt += cur + parts[i + 1]
    return PromptSpec(prompt, "chronological_order", ("reasoning", "answer"))


def _text_vision(sample: Sample, opts: dict) -> PromptSpec:
    ts = sample.raw["timeseries"]
    names = sample.raw.get("name_of_series")
    lines = []
    for i, values in enumerate(ts):
        name = names[i] if names and i < len(names) else f"Series {i + 1}"
        is_float = isinstance(values[0], float)
        vals = _stride(values, opts.get("text_stride", 1), is_float)
        vs = ", ".join(f"{v:.2f}" for v in vals) if is_float else ", ".join(f"{v}" for v in vals)
        lines.append(f"{name}: [{vs}]")
    text_ts = "\n".join(lines)
    prompt = f"""You are provided with time series data in BOTH text format and visual format (image).

**Text Representation:**
{text_ts}

**Question:**
{_question_with_image(sample, opts)}

**Options:**
{_choice_text(sample.choices)}

Analyze the time series using both the numerical data and the visualization. """
    return PromptSpec(prompt, "answer_selection", ("answer",))


# ---- abductive (농구 경기) -------------------------------------------------
def _abductive_parts(sample: Sample, opts: dict) -> dict:
    ctx = sample.raw["context"]
    ts = sample.raw["numerical_time_series"]
    past = "Past Events (History):\n"
    for t, e in zip(ctx["history_times"], ctx["history_events"]):
        past += f"- {t}: {e}\n"
    future = "Future Events:\n"
    for t, e in zip(ctx["future_times"], ctx["future_events"]):
        future += f"- {t}: {e}\n"

    all_times = ctx["history_times"] + ctx["future_times"]
    a = ts["wp_Team A"]["history"] + ts["wp_Team A"]["future"]
    b = ts["wp_Team B"]["history"] + ts["wp_Team B"]["future"]
    table = "\nTime Series Data (Win Probability):\n"
    table += "Time | Team A Win Prob | Team B Win Prob\n"
    table += "-" * 60 + "\n"
    rows = [f"{t} | {a[i]:.3f} | {b[i]:.3f}\n" for i, t in enumerate(all_times)]
    table += "".join(_stride(rows, opts.get("text_stride", 1), True))

    choices = "\nOptions:\n"
    for i, c in enumerate(sample.choices):
        choices += f"{LABELS[i]}. {c}\n"
    return {"past": past.strip(), "future": future.strip(), "table": table.strip(), "choices": choices.strip()}


def _abductive_text(sample: Sample, opts: dict) -> PromptSpec:
    p = _abductive_parts(sample, opts)
    prompt = (
        "You are an expert in basketball game analysis. Your task is to perform abductive reasoning.\n"
        "Given a sequence of past events, future events, and corresponding time series data from a game, determine the most plausible event that occurred in between to link them.\n\n"
        "--- CONTEXT ---\n"
        f"{p['past']}\n"
        "\n... [A CRITICAL EVENT HAPPENED HERE] ...\n\n"
        f"{p['future']}\n\n"
        f"{p['table']}\n\n"
        "--- TASK ---\n"
        f"{sample.question}\n"
        f"{p['choices']}\n\n"
        "Based on the context, events, and time series data, what is the most likely event that happened? Please respond with a JSON object containing your reasoning and answer: {\"reasoning\": \"your step-by-step thinking\", \"answer\": \"X\"}."
    )
    return PromptSpec(prompt, "chronological_order", ("reasoning", "answer"))


def _abductive_vision(sample: Sample, opts: dict) -> PromptSpec:
    p = _abductive_parts(sample, opts)
    prompt = f"""You are an expert in basketball game analysis. Your task is to perform abductive reasoning.
Given a sequence of past events, future events, and corresponding time series data from a game, determine the most plausible event that occurred in between to link them.

--- CONTEXT ---
{p['past']}

... [A CRITICAL EVENT HAPPENED HERE] ...

{p['future']}

The image shows the win probability time series for both teams over the course of events. The vertical line marks the critical moment.

--- TASK ---
{sample.question}

{p['choices']}

Based on the context, events, and time series data in the image, what is the most likely event that happened? Please respond with a JSON object containing your reasoning and answer letter: e.g., {{ "answer": "A"}}."""
    return PromptSpec(prompt, "abductive_reasoning", ("reasoning", "answer"))


def _abductive_text_vision(sample: Sample, opts: dict) -> PromptSpec:
    p = _abductive_parts(sample, opts)
    prompt = (
        "You are an expert in basketball game analysis. Your task is to perform abductive reasoning.\n"
        "Given a sequence of past events, future events, and corresponding time series data from a game, determine the most plausible event that occurred in between to link them.\n\n"
        "--- CONTEXT ---\n"
        f"{p['past']}\n"
        "\n... [A CRITICAL EVENT HAPPENED HERE] ...\n\n"
        f"{p['future']}\n\n"
        f"{p['table']}\n\n"
        "The accompanying image also shows the win probability time series for both teams. "
        "The solid lines represent history, dashed lines represent future, and the vertical green line marks the critical moment.\n\n"
        "--- TASK ---\n"
        f"{sample.question}\n"
        f"{p['choices']}\n\n"
        "Based on the context, events, time series data (both in text and visual format), what is the most likely event that happened? "
        "Please only respond with a JSON object containing your answer without any other explanations: {\"answer\": \"X\"}."
    )
    return PromptSpec(prompt, "abductive_reasoning", ("reasoning", "answer"))


_BUILDERS = {
    ("generic", "vision"): _vision,
    ("generic", "text"): _text,
    ("generic", "text+vision"): _text_vision,
    ("abductive", "vision"): _abductive_vision,
    ("abductive", "text"): _abductive_text,
    ("abductive", "text+vision"): _abductive_text_vision,
}


def build(sample: Sample, modality: str, opts: dict) -> PromptSpec:
    try:
        fn = _BUILDERS[(sample.kind, modality)]
    except KeyError:
        raise ValueError(f"지원하지 않는 modality: {modality}") from None
    return fn(sample, opts)
