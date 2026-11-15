"""전체 흐름: 실행 -> 재개 -> 설정 변경 -> 보고서. 가짜 OpenAI-compatible 서버와 mock 모델을 쓴다."""
import json
import os
import subprocess
import sys
import time

import pytest
import yaml

from ts2img.config import expand
from ts2img.paths import ROOT, experiment_dir, reports_dir
from ts2img.runner import RunOptions, run_experiment
from ts2img.store import RunStore, read_json

from conftest import FakeOpenAI


def _records(exp, i=0):
    return RunStore(expand(exp)[i].run_dir).load()


def _lines(exp, i=0):
    p = expand(exp)[i].run_dir / "predictions.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# ---- 요청 형식 -------------------------------------------------------------
def test_request_follows_official_format(fake_server, make_exp):
    exp = make_exp(models=["fake"], modalities=["vision"], limit=3)
    assert run_experiment(exp) == 0
    assert len(fake_server.requests) == 3
    body = fake_server.requests[0]
    assert body["model"] == "fake-vlm"
    # 공식 코드처럼 sampling 값을 보내지 않는다 (서버 기본값 사용)
    assert not {"temperature", "top_p", "seed", "top_k"} & set(body)
    assert "max_tokens" not in body and "max_completion_tokens" not in body   # 공식 코드처럼 상한을 보내지 않는다
    rf = body["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"]["required"] == ["reasoning", "answer"]
    assert len(body["messages"]) == 1 and body["messages"][0]["role"] == "user"
    content = body["messages"][0]["content"]
    assert [c["type"] for c in content] == ["text", "image_url"]          # 공식 순서: text 다음 이미지
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[0]["text"].endswith("Output your reasoning and answer in JSON format.")

    run_dir = expand(exp)[0].run_dir
    for name in ("predictions.jsonl", "config.json", "env.json", "summary.json", "request_samples.json"):
        assert (run_dir / name).is_file(), name
    assert len(list((run_dir / "chart_samples").glob("*.jpg"))) == 3
    cfg = read_json(run_dir / "config.json")
    assert cfg["identity"]["sampling"] == "official" and cfg["endpoint"]["models"] == ["fake-vlm"]
    # 기록에 key 나 URL 의 비밀 값이 들어가지 않는다
    assert "api_key" not in json.dumps(cfg).lower()


def test_text_modality_sends_no_image(fake_server, make_exp):
    exp = make_exp(models=["fake"], modalities=["text"], limit=2)
    assert run_experiment(exp) == 0
    for body in fake_server.requests:
        assert [c["type"] for c in body["messages"][0]["content"]] == ["text"]


def test_deterministic_sampling_is_sent(fake_server, make_exp):
    exp = make_exp(models=["fake"], sampling="deterministic", limit=1)
    assert run_experiment(exp) == 0
    assert fake_server.requests[0]["temperature"] == 0 and fake_server.requests[0]["seed"] == 0


# ---- 재개, 설정 변경 -------------------------------------------------------
def test_rerun_skips_done_and_limit_extends(fake_server, make_exp):
    exp = make_exp(models=["fake"], limit=4)
    assert run_experiment(exp) == 0
    assert len(fake_server.requests) == 4
    assert run_experiment(exp) == 0                      # 다시 실행: 요청 없음
    assert len(fake_server.requests) == 4

    more = make_exp(models=["fake"], limit=7)            # 문항만 늘림: 같은 폴더에 3문항만 추가
    assert expand(more)[0].run_dir == expand(exp)[0].run_dir
    assert run_experiment(more) == 0
    assert len(fake_server.requests) == 7
    assert len(_lines(more)) == 7 and len(_records(more)) == 7


def test_config_change_uses_new_folder(fake_server, make_exp):
    a = make_exp(models=["fake"], limit=3)
    b = make_exp(models=["fake"], limit=3, charts=[{"use": "line_style", "linewidth": 4}])
    assert run_experiment(a) == 0 and run_experiment(b) == 0
    assert expand(a)[0].run_dir != expand(b)[0].run_dir
    assert len(fake_server.requests) == 6
    assert len(_records(a)) == 3 and len(_records(b)) == 3


def test_failed_requests_are_retried_next_run(fake_server, make_exp, monkeypatch):
    monkeypatch.setattr("ts2img.models.client.time.sleep", lambda s: None)   # backoff 대기 생략
    state = {"n": 0}

    def flaky(body):
        state["n"] += 1
        return (500, FakeOpenAI.error("boom", "server_error")) if state["broken"] else (200, FakeOpenAI.answer("B"))

    state["broken"] = True
    fake_server.reply = flaky
    exp = make_exp(models=["fake"], limit=4, concurrency=2)
    run_experiment(exp)
    recs = _records(exp)
    assert len(recs) == 4 and all(r["status"] == "error" for r in recs.values())

    state["broken"] = False                               # 서버 복구 후 같은 명령
    assert run_experiment(exp) == 0
    recs = _records(exp)
    assert all(r["status"] == "ok" and r["pred"] == "B" for r in recs.values())


def test_context_overflow_is_final(fake_server, make_exp):
    fake_server.reply = lambda body: (400, FakeOpenAI.error("This model's maximum context length is 8192 tokens. However, you requested 20000 tokens"))
    exp = make_exp(models=["fake"], modalities=["text"], limit=3)
    assert run_experiment(exp) == 0
    n = len(fake_server.requests)
    assert n == 3                                          # 재시도하지 않는다
    assert all(r["status"] == "context_overflow" and not r["correct"] for r in _records(exp).values())
    assert run_experiment(exp) == 0                        # 다음 실행에서도 다시 보내지 않는다
    assert len(fake_server.requests) == n
    assert read_json(expand(exp)[0].run_dir / "summary.json")["acc"] == 0.0   # 오답으로 집계


def test_overflow_retried_when_context_limit_changes(fake_server, make_exp, tmp_path, monkeypatch):
    def write_models(max_len):
        p = tmp_path / "models.yaml"
        p.write_text(f"models:\n  served:\n    model: fake-vlm\n    base_url: {fake_server.url}\n"
                     f"    serve: {{max_model_len: {max_len}, dtype: float16}}\n", encoding="utf-8")
        monkeypatch.setenv("TS2IMG_MODELS_FILE", str(p))

    write_models(8192)
    fake_server.reply = lambda body: (400, FakeOpenAI.error("maximum context length is 8192 tokens"))
    exp = make_exp(models=["served"], modalities=["text"], limit=3)
    assert run_experiment(exp) == 0
    run_dir = expand(exp)[0].run_dir
    assert all(r["status"] == "context_overflow" and r["ctx_limit"] == 8192 for r in _records(exp).values())
    assert run_experiment(exp) == 0 and len(fake_server.requests) == 3        # 같은 한도: 다시 보내지 않는다

    write_models(32768)                                                        # 한도를 올림
    fake_server.reply = lambda body: (200, FakeOpenAI.answer("A"))
    exp = make_exp(models=["served"], modalities=["text"], limit=3)
    assert expand(exp)[0].run_dir == run_dir                                   # 같은 run 폴더
    assert run_experiment(exp) == 0 and len(fake_server.requests) == 6        # 넘쳤던 문항만 다시
    assert all(r["status"] == "ok" for r in _records(exp).values())


def test_retry_overflow_flag(fake_server, make_exp):
    fake_server.reply = lambda body: (400, FakeOpenAI.error("maximum context length is 8192 tokens"))
    exp = make_exp(models=["fake"], modalities=["text"], limit=2)
    assert run_experiment(exp) == 0 and len(fake_server.requests) == 2
    fake_server.reply = lambda body: (200, FakeOpenAI.answer("A"))
    assert run_experiment(exp) == 0 and len(fake_server.requests) == 2
    assert run_experiment(exp, RunOptions(retry_overflow=True)) == 0 and len(fake_server.requests) == 4
    assert all(r["status"] == "ok" for r in _records(exp).values())


def test_auth_failure_stops_model(fake_server, make_exp):
    fake_server.reply = lambda body: (401, FakeOpenAI.error("Incorrect API key", "invalid_api_key"))
    exp = make_exp(models=["fake"], limit=6, concurrency=1)
    assert run_experiment(exp) == 1
    assert len(fake_server.requests) <= 2                  # 계속 두드리지 않는다
    assert read_json(experiment_dir(exp.name) / "status.json")["state"] == "failed"


def test_unparseable_answer_is_requested_again(fake_server, make_exp):
    seen = {}

    def reply(body):
        key = body["messages"][0]["content"][0]["text"]
        seen[key] = seen.get(key, 0) + 1
        return (200, FakeOpenAI.answer("C") if seen[key] >= 3 else FakeOpenAI.answer("", raw="hmm, hard to say"))

    fake_server.reply = reply
    exp = make_exp(models=["fake"], limit=2, concurrency=1)
    assert run_experiment(exp) == 0
    assert all(r["attempts"] == 3 and r["pred"] == "C" for r in _records(exp).values())

    # temperature 0 이면 다시 물어도 같으므로 재요청하지 않는다
    fake_server.reply = lambda body: (200, FakeOpenAI.answer("", raw="hmm"))
    det = make_exp(models=["fake"], limit=2, sampling="deterministic")
    assert run_experiment(det) == 0
    assert all(r["attempts"] == 1 and r["pred"] is None for r in _records(det).values())


def test_missing_api_key_message(make_exp, tmp_path, monkeypatch):
    models = tmp_path / "models.yaml"
    models.write_text("models:\n  nokey:\n    model: m\n    base_url: http://127.0.0.1:9/v1\n    api_key_env: TS2IMG_TEST_NO_SUCH_KEY\n", encoding="utf-8")
    monkeypatch.setenv("TS2IMG_MODELS_FILE", str(models))
    assert run_experiment(make_exp(models=["nokey"], limit=2)) == 1


# ---- 프로세스가 죽은 뒤 이어서 실행 ----------------------------------------
def test_kill_and_resume(tmp_path):
    cfg = {"benchmarks": ["tsrbench/perception"], "models": ["mock"], "modalities": ["text"], "limit": 60, "concurrency": 2}
    path = tmp_path / "killme.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    env = {**os.environ, "TS2IMG_RESULTS_DIR": str(tmp_path / "results"), "TS2IMG_MOCK_DELAY": "0.1", "PYTHONIOENCODING": "utf-8"}
    cmd = [sys.executable, "-m", "ts2img", "run", str(path)]
    pred = None
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            found = list((tmp_path / "results" / "runs").rglob("predictions.jsonl"))
            if found and len(found[0].read_text(encoding="utf-8").splitlines()) >= 10:
                pred = found[0]
                break
            assert proc.poll() is None, "실행이 너무 일찍 끝났습니다"
            time.sleep(0.2)
        assert pred is not None
    finally:
        proc.kill()                                       # 정리할 틈 없이 강제 종료
        proc.wait()
    before = len(pred.read_text(encoding="utf-8").splitlines())
    assert 10 <= before < 60
    st = read_json(tmp_path / "results" / "experiments" / "killme" / "status.json")
    assert st["state"] == "running"                       # 죽은 채로 남은 기록

    env.pop("TS2IMG_MOCK_DELAY")
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    lines = [json.loads(x) for x in pred.read_text(encoding="utf-8").splitlines() if x.strip()]
    ids = [x["id"] for x in lines]
    assert len(ids) == 60 and len(set(ids)) == 60         # 빠진 문항도, 두 번 돈 문항도 없다
    assert all(x["status"] == "ok" for x in lines)
    assert read_json(tmp_path / "results" / "experiments" / "killme" / "status.json")["state"] == "finished"


def test_background_run_status_stop(tmp_path):
    cfg = {"benchmarks": ["tsrbench/perception"], "models": ["mock"], "modalities": ["text"], "limit": 400, "concurrency": 2}
    path = tmp_path / "bg.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    env = {**os.environ, "TS2IMG_RESULTS_DIR": str(tmp_path / "results"), "TS2IMG_MOCK_DELAY": "0.2", "PYTHONIOENCODING": "utf-8"}
    base = [sys.executable, "-m", "ts2img"]
    status_path = tmp_path / "results" / "experiments" / "bg" / "status.json"

    def run(*args):
        return subprocess.run(base + list(args), cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")

    r = run("run", str(path), "--background")
    assert r.returncode == 0, r.stdout + r.stderr          # 바로 돌아온다
    deadline = time.time() + 60
    while time.time() < deadline and (read_json(status_path) or {}).get("requests_done", 0) < 4:
        time.sleep(0.3)
    st = read_json(status_path)
    assert st and st["state"] == "running" and 0 < st["requests_done"] < 400
    assert run("run", str(path)).returncode == 2            # 같은 실험을 동시에 두 번 돌리지 않는다
    assert "실행 중" in run("status", "bg").stdout
    assert run("stop", "bg").returncode == 0
    assert read_json(status_path)["state"] == "interrupted"
    assert (status_path.parent / "stdout.log").is_file() and (status_path.parent / "run.log").is_file()

    env.pop("TS2IMG_MOCK_DELAY")
    assert run("run", str(path)).returncode == 0            # 이어서 끝까지
    assert read_json(status_path)["state"] == "finished"


def test_truncated_last_line_is_ignored(make_exp):
    exp = make_exp(limit=5)
    assert run_experiment(exp) == 0
    p = expand(exp)[0].run_dir / "predictions.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write('{"id": "perception#5", "status": "ok", "corr')   # 쓰다가 죽은 줄
    more = make_exp(limit=7)
    assert run_experiment(more) == 0
    assert len(_records(more)) == 7


# ---- 보고서 ----------------------------------------------------------------
def test_report(make_exp):
    from ts2img.report.build import build_report

    exp = make_exp(
        "rep", benchmarks=["tsrbench/perception", "tsrbench/reasoning/abductive"], modalities=["text", "vision", "text+vision"],
        charts=["tsrbench_baseline", {"use": "line_style", "linewidth": 4}, {"use": "multi_view", "views": ["full", "diff"]}],
        repeats=2, limit=12, concurrency=8,
    )
    assert run_experiment(exp) == 0
    out = build_report(exp)
    assert out == reports_dir() / "rep"
    md = (out / "report.md").read_text(encoding="utf-8")
    for needle in ("## tsrbench / mock / vision", "## tsrbench / mock / text+vision", "text (chart 없음)", "(baseline)",
                   "line_style(linewidth=4)", "실행 간 변동", "McNemar", "실행 환경과 설정", "최빈 정답"):
        assert needle in md, needle
    assert (out / "summary.csv").is_file() and (out / "report.html").is_file()
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "data:image/jpeg;base64," in html and 'src="figures/' not in html   # 이미지가 파일 안에 들어 있다
    assert list((out / "figures").glob("gallery_*.jpg")) and list((out / "figures").glob("accuracy_*.png"))
    assert sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) < 3_000_000   # 보고서는 git 에 올린다


def test_report_on_partial_results(make_exp):
    from ts2img.report.build import build_report

    assert run_experiment(make_exp("part", limit=4)) == 0
    bigger = make_exp("part", limit=9, charts=["tsrbench_baseline", {"use": "moving_average"}])
    md = (build_report(bigger) / "report.md").read_text(encoding="utf-8")
    assert "미완료" in md


# ---- CLI -------------------------------------------------------------------
def test_cli_commands(make_exp, tmp_path, capsys):
    from ts2img.cli import main

    assert main(["list"]) == 0
    assert main(["doctor"]) == 0
    exp_path = str(make_exp("cli", limit=3).source)
    assert main(["run", exp_path, "--dry-run"]) == 0
    assert main(["run", exp_path]) == 0
    assert main(["status", "cli"]) == 0
    assert main(["report", exp_path]) == 0
    assert main(["preview", "prompt", "--task", "tsrbench/reasoning/numerical", "--modality", "text+vision"]) == 0
    out = tmp_path / "g.png"
    assert main(["preview", "charts", "--task", "tsrbench/perception", "--n", "2",
                 "--charts", "tsrbench_baseline", "{use: line_style, linewidth: 4}", "--out", str(out)]) == 0
    assert out.is_file()
    assert main(["run", "no_such_experiment"]) == 2
    assert main(["run", exp_path, "--models", "no_such_model"]) == 2
    assert main(["serve", "start", "qwen3-vl-4b", "--dry-run"]) == 0
    assert main(["stop", "cli"]) == 0
    capsys.readouterr()


def test_sync_roundtrip(make_exp, tmp_path):
    from ts2img import sync
    from ts2img.paths import results_dir

    exp = make_exp(limit=3)
    assert run_experiment(exp) == 0
    drive = tmp_path / "drive"
    n = sync.push(drive)
    assert n > 0 and sync.push(drive) == 0                # 바뀐 파일만 복사
    import shutil

    shutil.rmtree(results_dir())                          # Colab VM 이 초기화된 상황
    assert sync.restore(drive) == n
    assert len(_records(exp)) == 3
