"""테스트 공통 설정. 결과는 임시 폴더에 쓰고, 데이터는 저장소의 data/ 를 그대로 쓴다."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@pytest.fixture(autouse=True)
def _isolated_results(tmp_path, monkeypatch):
    monkeypatch.setenv("TS2IMG_RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.delenv("TS2IMG_MOCK_DELAY", raising=False)
    monkeypatch.delenv("TS2IMG_SYNC_DIR", raising=False)


class FakeOpenAI:
    """OpenAI-compatible 서버 흉내. reply(body) 가 (status, json) 을 돌려준다."""

    def __init__(self):
        self.requests: list[dict] = []
        self.reply = lambda body: (200, self.answer("A"))
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, obj):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send(200, {"object": "list", "data": [{"id": "fake-vlm", "object": "model"}]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with outer._lock:
                    outer.requests.append(body)
                status, obj = outer.reply(body)
                self._send(status, obj)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @staticmethod
    def answer(letter: str, raw: str | None = None) -> dict:
        content = raw if raw is not None else json.dumps({"reasoning": "because", "answer": letter})
        return {
            "id": "x", "object": "chat.completion", "model": "fake-vlm",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        }

    @staticmethod
    def error(message: str, code: str = "bad_request") -> dict:
        return {"error": {"message": message, "type": code, "code": code}}

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    """가짜 서버와 그 서버를 가리키는 models.yaml (key: fake)."""
    srv = FakeOpenAI()
    models = tmp_path / "models.yaml"
    models.write_text(f"models:\n  fake:\n    model: fake-vlm\n    base_url: {srv.url}\n", encoding="utf-8")
    monkeypatch.setenv("TS2IMG_MODELS_FILE", str(models))
    yield srv
    srv.close()


@pytest.fixture
def make_exp(tmp_path):
    """실험 yaml 을 임시 파일로 만들어 Experiment 로 읽는다."""
    import yaml

    from ts2img.config import load_experiment

    def _make(name="t", **kw):
        cfg = {"benchmarks": ["tsrbench/perception"], "models": ["mock"], "modalities": ["vision"],
               "charts": ["tsrbench_baseline"], "limit": 6, "concurrency": 4, **kw}
        p = tmp_path / f"{name}.yaml"
        p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        return load_experiment(p)

    return _make
