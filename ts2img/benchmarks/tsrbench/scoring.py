"""객관식 채점.

공식 evaluation/evaluate.py 의 evaluate_MCQ 와 같은 규칙으로 답을 뽑되 eval() 은 쓰지 않는다.
- parse == "json":     응답이 "answer" 를 가진 dict 로 읽힌 경우 (공식 채점이 인정하는 경우)
- parse == "fallback": dict 로는 안 읽히지만 답 글자를 찾은 경우 (공식 채점은 제외)
- parse is None:       답을 찾지 못함

JSON 으로 시작했는데 읽히지 않는 응답(대개 길이 한도에서 잘린 것)은 "answer" 항목이 있을 때만 답으로 인정한다.
풀이 본문에 나온 "option C is incorrect" 같은 표현을 답으로 집으면 안 된다.
"""
from __future__ import annotations

import ast
import json
import re

from ts2img.benchmarks.base import Score

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)
_ANSWER_FIELD = re.compile(r"""["']?answer["']?\s*[:=]\s*["'(\s]*([A-Za-z])\b""", re.I)
_LEADING = re.compile(r"^\s*\(?([A-Ga-g])\s*[\).:]")
_FINAL = re.compile(r"(?:answer|option)\s*(?:is|:)?\s*\(?([A-G])\)?(?![A-Za-z])")
# JSON 안의 "answer" 항목. 풀이 문자열 안에서는 따옴표가 \" 로 적히므로 걸리지 않는다
_JSON_ANSWER = re.compile(r"""["']answer["']\s*:\s*["']\s*\(?([A-Za-z])\b""", re.I)


def _as_dict(response: str) -> dict | None:
    text = _FENCE.sub("", response.strip()).strip()
    for loader in (json.loads, ast.literal_eval):
        try:
            obj = loader(text)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    # 앞뒤에 설명이 붙은 경우: 가장 바깥 중괄호만 다시 시도
    i, j = text.find("{"), text.rfind("}")
    if 0 <= i < j:
        try:
            obj = json.loads(text[i : j + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None


def _letter(answer) -> str | None:
    """공식 규칙: 일부 기호를 지운 뒤 첫 글자."""
    s = str(answer)
    for ch in (",", "$", " ", "*", "(", ")"):
        s = s.replace(ch, "")
    s = s.strip()
    return s[0].upper() if s and s[0].isalpha() else None


def extract(response: str | None) -> tuple[str | None, str | None]:
    """(답 글자, parse 방식) 을 돌려준다."""
    if not response or not response.strip():
        return None, None
    obj = _as_dict(response)
    if obj is not None and "answer" in obj:
        letter = _letter(obj["answer"])
        # dict 로 읽혔으면 공식 채점 대상이다. 글자를 못 뽑으면 오답 처리된다
        return letter, "json"
    text = _FENCE.sub("", response.strip()).strip()
    if text.startswith("{"):
        # 읽히지 않는 JSON: "answer" 항목까지 쓴 경우만 인정한다 (마지막 것)
        found = _JSON_ANSWER.findall(text)
        return (found[-1].upper(), "fallback") if found else (None, None)
    # JSON 이 아닌 글: 형식이 분명한 것부터 찾는다. "answer is X" 는 결론이 뒤에 오므로 마지막 것을 쓴다
    for pat in (_ANSWER_FIELD, _LEADING):
        m = pat.search(text)
        if m:
            return m.group(1).upper(), "fallback"
    found = _FINAL.findall(text)
    if found:
        return found[-1].upper(), "fallback"
    return None, None


def score(label: str, response: str | None) -> Score:
    pred, parse = extract(response)
    correct = pred is not None and pred.lower() == str(label).strip().lower()[:1]
    return Score(pred=pred, correct=correct, parse=parse)
