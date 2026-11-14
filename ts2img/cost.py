"""상용 모델 비용 계산. 단가는 configs/pricing.yaml (USD / 1M tokens)."""
from __future__ import annotations

from ts2img.config import ModelSpec


def price_for(model: ModelSpec, pricing: dict) -> dict | None:
    p = pricing.get(model.key) or pricing.get(model.model)
    if not p or p.get("input") is None or p.get("output") is None:
        return None
    return {"input": float(p["input"]), "output": float(p["output"])}


def cost_of(rec: dict, price: dict | None) -> float:
    if not price:
        return 0.0
    return (rec.get("prompt_tokens") or 0) * price["input"] / 1e6 + (rec.get("completion_tokens") or 0) * price["output"] / 1e6


def project(records: list[dict], n_remaining: int, price: dict | None) -> dict | None:
    """끝난 문항의 평균 token 수로 남은 문항의 비용을 추정한다."""
    ok = [r for r in records if r.get("status") == "ok" and r.get("prompt_tokens")]
    if not ok or not price:
        return None
    avg_in = sum(r["prompt_tokens"] for r in ok) / len(ok)
    avg_out = sum(r.get("completion_tokens") or 0 for r in ok) / len(ok)
    per_sample = avg_in * price["input"] / 1e6 + avg_out * price["output"] / 1e6
    return {
        "based_on": len(ok), "avg_prompt_tokens": avg_in, "avg_completion_tokens": avg_out,
        "usd_per_sample": per_sample, "usd_remaining": per_sample * n_remaining,
    }
