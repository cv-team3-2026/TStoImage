"""TSRBench 방식: 질문(+ chart 이미지)을 한 번 보내고 답을 받는다.

yaml 예: method: single_turn
         method: {use: single_turn, image_captions: false}
"""
from __future__ import annotations

import base64

from ts2img import charts
from ts2img.methods.base import Request, RunContext
from ts2img.models.client import ContextOverflow, RequestFailed
from ts2img.store import now_iso

VERSION = 1


def build_request(sample, cell, benchmark, image_captions: bool = True) -> Request:
    images = []
    if "vision" in cell.modality:
        images = charts.render(sample, cell.chart.use, cell.chart.params, cell.chart.post) or []
    prompt = benchmark.prompt(sample, cell.modality, cell.prompt_opts())

    # 공식 코드와 같은 순서: text 다음에 이미지
    content = [{"type": "text", "text": prompt.text}]
    for i, img in enumerate(images):
        if image_captions and img.caption:
            content.append({"type": "text", "text": f"[Image {i + 1}] {img.caption}"})
        b64 = base64.b64encode(img.data).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{img.mime};base64,{b64}"}})

    mode = cell.response_format()
    if mode == "json_schema":
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": prompt.schema_name, "schema": prompt.response_schema()},
        }
    elif mode == "json_object":
        response_format = {"type": "json_object"}
    else:
        response_format = None
    return Request([{"role": "user", "content": content}], response_format, prompt.text, images)


def run_sample(sample, ctx: RunContext, image_captions: bool = True) -> dict:
    cell, exp = ctx.cell, ctx.cell.exp
    rec = {
        "id": sample.id, "idx": sample.idx, "task": sample.task, "answer": sample.answer,
        "pred": None, "parse": None, "correct": False, "status": "error", "ts": now_iso(),
    }
    try:
        req = build_request(sample, cell, ctx.benchmark, image_captions=image_captions)
    except Exception as e:  # chart 나 prompt 생성 실패
        rec["error"] = f"build_request: {type(e).__name__}: {e}"
        return rec
    rec["prompt_sha"] = req.prompt_sha
    rec["prompt_chars"] = len(req.prompt_text)
    rec["images"] = [{"sha": im.sha, "size": list(im.size), "bytes": len(im.data), "mime": im.mime} for im in req.images]
    if ctx.capture:
        ctx.capture(sample, req)

    # 공식 코드: 답이 한 글자로 안 나오면 최대 10번 다시 요청한다.
    # temperature 0 이면 같은 답이 나오므로 다시 요청하지 않는다
    retries = 0 if exp.deterministic else max(0, exp.answer_retries)
    prompt_tokens = completion_tokens = 0
    latency = 0.0
    try:
        for attempt in range(retries + 1):
            comp = ctx.client.complete(
                req.messages, response_format=req.response_format,
                sampling=exp.sampling_params(cell.repeat), max_tokens=exp.max_tokens,
            )
            prompt_tokens += comp.prompt_tokens or 0
            completion_tokens += comp.completion_tokens or 0
            latency += comp.latency_s
            score = ctx.benchmark.score(sample, comp.text)
            if score.pred is not None:
                break
    except ContextOverflow as e:
        # 한도를 같이 적어 둔다. 나중에 한도를 올리면 이 문항만 다시 시도한다
        rec.update(status="context_overflow", error=str(e), ctx_limit=cell.model.context_limit)
        return rec
    except RequestFailed as e:
        rec["error"] = str(e)
        return rec

    rec.update(
        status="ok", pred=score.pred, parse=score.parse, correct=score.correct, response=comp.text,
        attempts=attempt + 1, finish_reason=comp.finish_reason, latency_s=round(latency, 3),
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        last_prompt_tokens=comp.prompt_tokens,
    )
    return rec
