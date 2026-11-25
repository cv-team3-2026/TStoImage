"""로컬 VLM 서빙 (vLLM, OpenAI-compatible).

models.yaml 의 serve 블록을 vLLM 명령으로 바꿔 백그라운드로 띄운다.
vLLM 은 실험 실행 환경과 충돌하지 않게 별도 venv 에 설치한다 (serve setup).
Linux + NVIDIA GPU 에서만 동작한다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from ts2img import ui
from ts2img.config import ModelSpec
from ts2img.paths import ROOT, serve_dir
from ts2img.store import now_iso, read_json, write_json

DEFAULT_VENV = Path.home() / ".cache" / "ts2img" / "serve-venv"


def venv_dir() -> Path:
    return Path(os.environ.get("TS2IMG_SERVE_VENV") or DEFAULT_VENV)


def venv_python() -> Path:
    return venv_dir() / "bin" / "python"


def _state_path() -> Path:
    return serve_dir() / "state.json"


def _check_platform() -> None:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("vLLM 서빙은 Linux + NVIDIA GPU 에서만 됩니다. 이 PC 에서는 외부 endpoint URL 이나 상용 API 를 쓰세요.")


def setup(force: bool = False) -> None:
    """별도 venv 를 만들고 requirements-serve.txt 를 설치한다. 이미 있으면 건너뛴다."""
    _check_platform()
    py = venv_python()
    if py.is_file() and not force:
        r = subprocess.run([str(py), "-c", "import vllm; print(vllm.__version__)"], capture_output=True, text=True)
        if r.returncode == 0:
            ui.ok(f"vLLM {r.stdout.strip()} 이미 설치됨: {venv_dir()}")
            return
    if not shutil.which("uv"):
        ui.info("uv 설치")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
    uv = [shutil.which("uv")] if shutil.which("uv") else [sys.executable, "-m", "uv"]
    ui.info(f"venv 생성: {venv_dir()} (몇 분 걸립니다)")
    subprocess.run([*uv, "venv", str(venv_dir()), "--python", "3.12", "--seed"], check=True)
    subprocess.run(
        [*uv, "pip", "install", "--python", str(py), "-r", str(ROOT / "requirements-serve.txt")], check=True
    )
    ui.ok("vLLM 설치 완료")


def _gpu_list(serve: dict) -> list[int]:
    gpus = serve.get("gpus", [0])
    if isinstance(gpus, int):
        return [gpus]
    if isinstance(gpus, str):
        return [int(x) for x in gpus.split(",") if x.strip() != ""]
    return [int(x) for x in gpus]


def build_command(spec: ModelSpec, python: str | None = None) -> tuple[list[str], dict]:
    """serve 블록 -> (vLLM 명령, 추가 환경변수)."""
    s = spec.serve or {}
    gpus = _gpu_list(s)
    cmd = [
        python or str(venv_python()), "-m", "vllm.entrypoints.openai.api_server",
        "--model", spec.model,
        "--served-model-name", spec.model,
        "--host", str(s.get("host", "127.0.0.1")),
        "--port", str(s.get("port", 8000)),
        "--tensor-parallel-size", str(s.get("tensor_parallel_size", len(gpus))),
    ]
    if s.get("revision"):
        cmd += ["--revision", str(s["revision"])]
    if s.get("dtype"):
        cmd += ["--dtype", str(s["dtype"])]
    if s.get("quantization"):
        cmd += ["--quantization", str(s["quantization"])]
    if s.get("max_model_len"):
        cmd += ["--max-model-len", str(s["max_model_len"])]
    if s.get("gpu_memory_utilization"):
        cmd += ["--gpu-memory-utilization", str(s["gpu_memory_utilization"])]
    if s.get("limit_mm_per_prompt"):
        cmd += ["--limit-mm-per-prompt", json.dumps(s["limit_mm_per_prompt"])]
    if s.get("generation_config"):
        cmd += ["--generation-config", str(s["generation_config"])]
    if s.get("trust_remote_code"):
        cmd += ["--trust-remote-code"]
    cmd += [str(a) for a in s.get("extra_args", [])]
    env = {"CUDA_VISIBLE_DEVICES": ",".join(str(g) for g in gpus)}
    env.update({k: str(v) for k, v in (s.get("env") or {}).items()})
    return cmd, env


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil

        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except Exception:
        return False


def _ready(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _tail(path: Path, n: int = 30) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except Exception:
        return ""


def current() -> dict | None:
    """지금 떠 있는 서버 정보. 없으면 None."""
    st = read_json(_state_path())
    if st and _alive(st.get("pid")):
        return st
    return None


def start(spec: ModelSpec, wait: bool = True) -> dict:
    _check_platform()
    if not spec.serve:
        raise ValueError(f"{spec.key}: models.yaml 에 serve 블록이 없습니다 (직접 띄우는 모델이 아님)")
    cur = current()
    base_url = spec.resolved_base_url()
    if cur and cur["key"] == spec.key and _ready(base_url):
        ui.ok(f"이미 실행 중: {spec.key} (pid {cur['pid']}, {base_url})")
        return cur
    if cur:
        ui.info(f"다른 모델이 떠 있어 먼저 종료합니다: {cur['key']}")
        stop()
    if not venv_python().is_file():
        setup()
    from ts2img import secrets

    cmd, extra_env = build_command(spec)
    # venv 안의 ninja 가 PATH 에 없으면 FlashInfer JIT 가 서버 기동 중에 죽는다.
    env = {**os.environ, **extra_env}
    venv_bin = str(venv_dir() / "bin")
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    token = secrets.get("HF_TOKEN")
    if token:
        env["HF_TOKEN"] = token
    serve_dir().mkdir(parents=True, exist_ok=True)
    log_path = serve_dir() / f"{spec.key}.log"
    ui.panel(" ".join(cmd) + f"\n\nCUDA_VISIBLE_DEVICES={extra_env['CUDA_VISIBLE_DEVICES']}\nlog: {log_path}", title=f"vLLM 시작: {spec.key}")
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=ROOT)
    state = {
        "key": spec.key, "model": spec.model, "pid": proc.pid, "base_url": base_url, "log": str(log_path),
        "cmd": cmd, "env": extra_env, "started_at": now_iso(), "serve": spec.serve,
    }
    write_json(_state_path(), state)
    if wait:
        wait_ready(spec, state)
    return state


def wait_ready(spec: ModelSpec, state: dict) -> None:
    timeout = float((spec.serve or {}).get("startup_timeout_s", 1800))
    t0 = time.time()
    log_path = Path(state["log"])
    last_print = 0.0
    while True:
        if _ready(state["base_url"]):
            ui.ok(f"서버 준비 완료 ({ui.fmt_duration(time.time() - t0)}): {state['base_url']}")
            return
        if not _alive(state["pid"]):
            ui.error("vLLM 프로세스가 종료됐습니다. log 마지막 부분:")
            ui.console.print(_tail(log_path, 40), markup=False)
            raise RuntimeError("vLLM 시작 실패")
        if time.time() - t0 > timeout:
            stop()
            ui.console.print(_tail(log_path, 40), markup=False)
            raise RuntimeError(f"vLLM 이 {timeout:.0f}초 안에 준비되지 않았습니다")
        if time.time() - last_print > 20:
            last_print = time.time()
            tail = _tail(log_path, 1)
            ui.info(f"대기 중 {ui.fmt_duration(time.time() - t0)} | {tail[-100:]}")
        time.sleep(3)


def stop() -> bool:
    st = read_json(_state_path())
    if not st:
        return False
    pid = st.get("pid")
    if _alive(pid):
        import psutil

        try:
            parent = psutil.Process(pid)
            procs = parent.children(recursive=True) + [parent]
            for p in procs:
                p.terminate()
            _, alive = psutil.wait_procs(procs, timeout=20)
            for p in alive:
                p.kill()
        except Exception as e:
            ui.warn(f"종료 중 문제: {e}")
        ui.ok(f"서버 종료: {st.get('key')} (pid {pid})")
    try:
        _state_path().unlink()
    except FileNotFoundError:
        pass
    return True


def show_status() -> None:
    cur = current()
    if not cur:
        ui.info("떠 있는 서버가 없습니다.")
        return
    ui.kv_table(
        "vLLM 서버",
        [
            ("모델", f"{cur['key']} ({cur['model']})"),
            ("pid", cur["pid"]),
            ("URL", cur["base_url"]),
            ("준비됨", "예" if _ready(cur["base_url"]) else "아니오 (로딩 중)"),
            ("시작", cur["started_at"]),
            ("log", cur["log"]),
        ],
    )
