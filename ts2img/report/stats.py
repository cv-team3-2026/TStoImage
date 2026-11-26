"""집계와 통계. scipy 없이 계산한다."""
from __future__ import annotations

import math
from collections import Counter
from statistics import median


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """비율의 95% Wilson 신뢰구간."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar exact test (양측). b, c = 두 조건에서 정오가 엇갈린 문항 수."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni 보정 p-value."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


# 정확도 분모에 들어가는 상태. context 초과는 다시 해도 못 푸는 문항이므로 오답으로 친다.
# error(네트워크 등)는 다음 실행에서 다시 시도하므로 집계에서 뺀다.
_SCORED = ("ok", "context_overflow")


def paired(base: dict[str, dict], variant: dict[str, dict]) -> dict:
    """같은 문항끼리 비교. 두 조건 모두 처리가 끝난 문항만 쓴다."""
    ids = [i for i in base if i in variant and base[i].get("status") in _SCORED and variant[i].get("status") in _SCORED]
    b = sum(1 for i in ids if not base[i].get("correct") and variant[i].get("correct"))   # 틀림 -> 맞음
    c = sum(1 for i in ids if base[i].get("correct") and not variant[i].get("correct"))   # 맞음 -> 틀림
    n = len(ids)
    out = {"n": n, "gained": b, "lost": c, "diff": None, "diff_ci": None, "p": None}
    if n:
        d = (b - c) / n
        se = math.sqrt(max(0.0, (b + c) - (b - c) ** 2 / n)) / n
        out.update(diff=d, diff_ci=(d - 1.96 * se, d + 1.96 * se), p=mcnemar_exact(b, c))
        out["gained_ids"] = [i for i in ids if not base[i].get("correct") and variant[i].get("correct")]
        out["lost_ids"] = [i for i in ids if base[i].get("correct") and not variant[i].get("correct")]
    return out


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _mean_ci(xs: list[float]) -> tuple[float, float] | None:
    """평균의 95% 구간. 비율이 아니라 문항별 점수의 평균일 때 쓴다."""
    if not xs:
        return None
    n = len(xs)
    mid = sum(xs) / n
    if n < 2:
        return mid, mid
    var = sum((x - mid) ** 2 for x in xs) / (n - 1)
    half = 1.96 * math.sqrt(var / n)
    return max(0.0, mid - half), min(1.0, mid + half)


def summarize(records: list[dict]) -> dict:
    """run 하나(또는 그 일부)의 지표.

    acc:          처리가 끝난 문항(n_done) 중 정답 비율. 답을 못 뽑은 응답과 context 초과는 오답으로 친다.
    acc_official: 공식 채점 방식. dict 로 읽힌 응답만 분모에 넣는다.
    """
    ok = [r for r in records if r.get("status") == "ok"]
    scored = [r for r in records if r.get("status") in _SCORED]
    n_done = len(scored)
    as_json = [r for r in ok if r.get("parse") == "json"]
    correct = sum(1 for r in ok if r.get("correct"))
    correct_json = sum(1 for r in as_json if r.get("correct"))
    f1_mode = any("f1" in r for r in scored)
    if f1_mode:
        vals = [float(r.get("f1") or 0.0) for r in scored]
        acc = sum(vals) / len(vals)
        ci = _mean_ci(vals)
        json_vals = [float(r["f1"]) for r in as_json if r.get("f1") is not None]
        acc_official = sum(json_vals) / len(json_vals) if json_vals else None
    else:
        acc = correct / n_done if n_done else None
        ci = wilson(correct, n_done)
        acc_official = correct_json / len(as_json) if as_json else None
    images = [im for r in ok for im in r.get("images") or []]
    latencies = [r["latency_s"] for r in ok if r.get("latency_s") is not None]
    return {
        "n": len(records),
        "n_ok": len(ok),
        "n_done": n_done,
        "n_error": sum(1 for r in records if r.get("status") == "error"),
        "n_overflow": sum(1 for r in records if r.get("status") == "context_overflow"),
        "correct": correct,
        "acc": acc,
        "ci": ci,
        "acc_official": acc_official,
        "no_answer": sum(1 for r in ok if r.get("pred") is None),
        "non_json": len(ok) - len(as_json),
        "truncated": sum(1 for r in ok if r.get("finish_reason") == "length"),
        "retried": sum(1 for r in ok if (r.get("attempts") or 1) > 1),
        "prompt_tokens": _mean([r["last_prompt_tokens"] for r in ok if r.get("last_prompt_tokens")]),
        "completion_tokens": _mean([r["completion_tokens"] / (r.get("attempts") or 1) for r in ok if r.get("completion_tokens")]),
        "total_prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in ok),
        "total_completion_tokens": sum(r.get("completion_tokens") or 0 for r in ok),
        "latency_median": median(latencies) if latencies else None,
        "latency_total": sum(latencies) if latencies else None,
        "image_bytes": _mean([im["bytes"] for im in images]),
        "image_size": Counter(tuple(im["size"]) for im in images).most_common(1)[0][0] if images else None,
        "images_per_sample": len(images) / len(ok) if ok else None,
    }


def majority_baseline(answers: list[str]) -> tuple[str, float] | None:
    """가장 흔한 정답 하나만 찍었을 때의 정확도."""
    if not answers:
        return None
    letter, k = Counter(answers).most_common(1)[0]
    return letter, k / len(answers)
