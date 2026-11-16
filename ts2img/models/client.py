"""OpenAI-compatible chat client. 상용 API, 외부 URL, 직접 띄운 vLLM 모두 같은 경로로 호출한다."""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass

from ts2img import secrets
from ts2img.config import ModelSpec

_OVERFLOW_HINTS = (
    "maximum context length", "context length", "context_length_exceeded", "context window",
    "too many tokens", "prompt is too long", "input is too long", "exceeds the maximum",
)


class ContextOverflow(Exception):
    """입력이 모델 context 한도를 넘음. 다시 시도해도 같으므로 재시도하지 않는다."""


class FatalModelError(Exception):
    """인증 실패, 모델 없음처럼 계속해도 소용없는 오류. 해당 모델의 실행을 멈춘다."""


class RequestFailed(Exception):
    """재시도 후에도 실패한 요청. 다음 실행에서 다시 시도한다."""


@dataclass
class Completion:
    text: str
    prompt_tokens: int | None
    completion_tokens: int | None
    finish_reason: str | None
    latency_s: float
    model: str | None = None


def request_kwargs(spec: ModelSpec, messages, *, response_format: dict | None, sampling: dict, max_tokens: int | None) -> dict:
    """chat.completions.create 에 넘기는 인자. sampling 이 비어 있으면 sampling 값을 보내지 않는다."""
    kwargs: dict = {"model": spec.model, "messages": messages}
    if response_format:
        kwargs["response_format"] = response_format
    if max_tokens:
        kwargs[spec.max_tokens_param] = max_tokens
    extra_body = dict(spec.request.get("extra_body") or {})
    for k, v in sampling.items():
        if k in ("temperature", "top_p", "seed"):
            kwargs[k] = v
        else:  # top_k 등 OpenAI 표준이 아닌 값
            extra_body[k] = v
    for k, v in spec.request.items():
        if k != "extra_body":
            kwargs[k] = v
    if extra_body:
        kwargs["extra_body"] = extra_body
    return kwargs


class ChatClient:
    def __init__(self, spec: ModelSpec, *, timeout: float = 600, max_retries: int = 6):
        self.spec = spec
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None
        if spec.provider == "mock":
            return
        if spec.provider != "openai":
            raise ValueError(f"모르는 provider: {spec.provider}")
        import openai

        base_url = spec.resolved_base_url()
        api_key = secrets.get(spec.api_key_env) if spec.api_key_env else "EMPTY"
        if spec.api_key_env and not api_key:
            raise FatalModelError(
                f"{spec.key}: API key '{spec.api_key_env}' 가 없습니다. secrets.env 또는 환경변수에 넣어 주세요."
            )
        if spec.base_url_env and not base_url:
            raise FatalModelError(f"{spec.key}: endpoint URL '{spec.base_url_env}' 가 없습니다.")
        # 재시도는 여기서 직접 한다 (횟수와 대기 시간을 기록하기 위해)
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)

    # ---- endpoint 확인 -----------------------------------------------------
    def ping(self) -> list[str]:
        """endpoint 가 제공하는 model 목록. 연결이 안 되면 FatalModelError."""
        if self.spec.provider == "mock":
            return [self.spec.model]
        import openai

        try:
            return [m.id for m in self._client.models.list().data]
        except openai.AuthenticationError as e:
            raise FatalModelError(f"{self.spec.key}: 인증 실패 ({e})") from e
        except openai.APIConnectionError as e:
            hint = " `python -m ts2img serve start` 로 먼저 띄워 주세요." if self.spec.serve else ""
            raise FatalModelError(f"{self.spec.key}: endpoint 에 연결할 수 없습니다: {self.spec.resolved_base_url()}{hint}") from e
        except Exception:
            return []  # /models 를 지원하지 않는 endpoint 도 있다

    # ---- 요청 --------------------------------------------------------------
    def build_kwargs(self, messages, *, response_format: dict | None, sampling: dict, max_tokens: int | None) -> dict:
        return request_kwargs(self.spec, messages, response_format=response_format, sampling=sampling, max_tokens=max_tokens)

    def complete(self, messages, *, response_format: dict | None = None, sampling: dict | None = None,
                 max_tokens: int | None = None) -> Completion:
        kwargs = self.build_kwargs(messages, response_format=response_format, sampling=sampling or {}, max_tokens=max_tokens)
        if self.spec.provider == "mock":
            return _mock_complete(kwargs)
        import openai

        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.time()
            try:
                resp = self._client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                usage = resp.usage
                return Completion(
                    text=choice.message.content or "",
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    finish_reason=choice.finish_reason,
                    latency_s=time.time() - t0,
                    model=getattr(resp, "model", None),
                )
            except (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError) as e:
                raise FatalModelError(f"{self.spec.key}: {type(e).__name__}: {e}") from e
            except (openai.BadRequestError, openai.UnprocessableEntityError) as e:
                msg = str(e).lower()
                if any(h in msg for h in _OVERFLOW_HINTS):
                    raise ContextOverflow(str(e)[:300]) from e
                raise RequestFailed(f"BadRequest: {str(e)[:500]}") from e
            except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as e:
                last = e
            except openai.APIStatusError as e:
                if e.status_code == 413:
                    raise ContextOverflow(str(e)[:300]) from e
                last = e
            if attempt < self.max_retries:
                time.sleep(min(60, 2 ** attempt) + random.uniform(0, 1))
        raise RequestFailed(f"{type(last).__name__}: {str(last)[:500]}")


def _mock_complete(kwargs: dict) -> Completion:
    """네트워크 없이 흐름을 확인하기 위한 가짜 응답. 요청 내용의 hash 로 답을 정한다."""
    delay = float(os.environ.get("TS2IMG_MOCK_DELAY") or 0)   # 테스트에서 느린 모델을 흉내낼 때
    if delay:
        time.sleep(delay)
    blob = json.dumps(kwargs["messages"], sort_keys=True, default=str) + json.dumps(kwargs.get("seed", 0))
    h = int(hashlib.sha256(blob.encode("utf-8")).hexdigest(), 16)
    letter = "ABCD"[h % 4]
    if h % 53 == 0:
        text = "I am not sure about the answer."      # 답 추출 실패 경로 확인용
    elif h % 17 == 0:
        text = f"{letter}) mock answer"               # JSON 이 아닌 응답
    else:
        text = json.dumps({"reasoning": "mock", "answer": letter})
    n_chars = sum(len(p.get("text", "")) for m in kwargs["messages"] for p in m["content"] if p.get("type") == "text")
    return Completion(text, prompt_tokens=n_chars // 4, completion_tokens=len(text) // 4,
                      finish_reason="stop", latency_s=0.0, model="mock")
