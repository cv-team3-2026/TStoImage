"""실행 환경 정보 수집. 호스트 이름과 사용자 이름은 모으지 않는다."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from importlib import metadata

from ts2img.paths import ROOT

_PACKAGES = ["matplotlib", "pillow", "numpy", "openai", "huggingface_hub", "PyYAML", "rich", "torch", "vllm"]


def _run(cmd: list[str], timeout: int = 15) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _cpu_name() -> str:
    if sys.platform.startswith("linux"):
        try:
            for line in open("/proc/cpuinfo", encoding="utf-8"):
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
    if sys.platform == "darwin":
        out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if out:
            return out
    return platform.processor() or platform.machine()


def gpus() -> list[dict]:
    """nvidia-smi 기준 GPU 목록. 없으면 빈 리스트."""
    if not shutil.which("nvidia-smi"):
        return []
    out = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    res = []
    for line in (out or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5:
            res.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_total_mb": int(float(parts[2])),
                    "memory_free_mb": int(float(parts[3])),
                    "driver": parts[4],
                }
            )
    return res


def tpu_detected() -> bool:
    return bool(os.environ.get("TPU_NAME") or os.environ.get("COLAB_TPU_ADDR") or os.environ.get("TPU_ACCELERATOR_TYPE"))


def in_colab() -> bool:
    return bool(os.environ.get("COLAB_RELEASE_TAG")) or "google.colab" in sys.modules


def git_state() -> dict:
    commit = _run(["git", "rev-parse", "HEAD"])
    dirty = _run(["git", "status", "--porcelain"])
    return {"commit": commit, "dirty": bool(dirty) if dirty is not None else None}


def package_versions() -> dict[str, str | None]:
    out = {}
    for p in _PACKAGES:
        try:
            out[p] = metadata.version(p)
        except Exception:
            out[p] = None
    return out


def collect(full: bool = False) -> dict:
    import psutil

    vm = psutil.virtual_memory()
    disk = shutil.disk_usage(ROOT)
    info = {
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "cpu": _cpu_name(),
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "ram_gb": round(vm.total / 2**30, 1),
        "ram_available_gb": round(vm.available / 2**30, 1),
        "disk_free_gb": round(disk.free / 2**30, 1),
        "gpus": gpus(),
        "tpu": tpu_detected(),
        "colab": in_colab(),
        "git": git_state(),
        "packages": package_versions(),
    }
    if full:
        info["pip_freeze"] = (_run([sys.executable, "-m", "pip", "freeze"], timeout=60) or "").splitlines()
    return info


def accelerator_summary(info: dict) -> str:
    if info["gpus"]:
        return ", ".join(f"GPU{g['index']} {g['name']} {g['memory_total_mb'] / 1024:.0f}GB" for g in info["gpus"])
    if info["tpu"]:
        return "TPU (VLM 서빙 미지원)"
    return "CPU only"


def show(info: dict | None = None) -> dict:
    from ts2img import ui

    info = info or collect()
    rows = [
        ("OS", info["os"]),
        ("Python", info["python"]),
        ("CPU", f"{info['cpu']} ({info['cpu_cores']} cores / {info['cpu_threads']} threads)"),
        ("RAM", f"{info['ram_gb']} GB (사용 가능 {info['ram_available_gb']} GB)"),
        ("Disk", f"여유 {info['disk_free_gb']} GB"),
        ("가속기", accelerator_summary(info)),
        ("Colab", "예" if info["colab"] else "아니오"),
        ("git", f"{(info['git']['commit'] or '?')[:8]}{' (수정 있음)' if info['git']['dirty'] else ''}"),
        ("패키지", ", ".join(f"{k} {v}" for k, v in info["packages"].items() if v)),
    ]
    ui.kv_table("실행 환경", rows)
    for g in info["gpus"]:
        ui.info(f"GPU{g['index']} {g['name']}: {g['memory_free_mb']} / {g['memory_total_mb']} MB 여유, driver {g['driver']}")
    if info["tpu"]:
        ui.warn("TPU 가 감지됐습니다. VLM 서빙은 GPU 에서만 됩니다. 실험 실행(요청 보내기)은 CPU 로 충분합니다.")
    if not info["gpus"]:
        ui.info("GPU 가 없습니다. 상용 API 나 외부 endpoint URL 로는 실험할 수 있습니다.")
    return info
