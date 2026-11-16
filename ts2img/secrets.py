"""API key 등 비밀 값 로더.

읽는 순서: 환경변수 -> Colab Secrets(노트북 kernel 안에서만) -> secrets.env
yaml 에는 key 이름만 적고 값은 여기서만 읽는다. 값은 출력하지 않는다.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from ts2img.paths import ROOT

SECRETS_FILE = ROOT / "secrets.env"

# 흔한 key 형태. doctor 가 git 에 올라갈 파일에서 찾는다
_KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"hf_[A-Za-z0-9]{30,}"),
]


def load_env_file(path: Path = SECRETS_FILE) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            out[k.strip()] = v
    return out


def _colab_get(name: str) -> str | None:
    # userdata 는 kernel 안에서만 동작한다. `!python ...` 하위 프로세스에서는 건너뛴다
    try:
        from IPython import get_ipython

        if get_ipython() is None:
            return None
        from google.colab import userdata  # type: ignore

        return userdata.get(name) or None
    except Exception:
        return None


def get(name: str | None) -> str | None:
    if not name:
        return None
    return os.environ.get(name) or _colab_get(name) or load_env_file().get(name)


def mask(value: str | None) -> str:
    if not value:
        return "(없음)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-2:]} ({len(value)}자)"


def export_colab_secrets(names: list[str] | None = None) -> list[str]:
    """Colab Secrets 를 환경변수로 복사한다. 노트북 셀에서 한 번 호출하면 `!python` 에서도 읽힌다."""
    if names is None:
        # models.yaml 을 직접 읽는다 (config 를 import 하면 kernel 에 matplotlib 까지 올라온다)
        import yaml

        path = Path(os.environ.get("TS2IMG_MODELS_FILE") or ROOT / "configs" / "models.yaml")
        models = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("models") or {}
        names = sorted({m[k] for m in models.values() if m for k in ("api_key_env", "base_url_env") if m.get(k)} | {"HF_TOKEN"})
    found = []
    for n in names:
        if os.environ.get(n):
            found.append(n)
            continue
        v = _colab_get(n)
        if v:
            os.environ[n] = v
            found.append(n)
    return found


def git_ignored(path: Path) -> bool | None:
    """git 이 해당 경로를 무시하는지. git 을 못 쓰면 None."""
    try:
        r = subprocess.run(
            ["git", "check-ignore", "-q", str(path)], cwd=ROOT, capture_output=True, timeout=10
        )
        return r.returncode == 0 if r.returncode in (0, 1) else None
    except Exception:
        return None


def scan_tracked_files() -> list[str]:
    """git 에 올라갔거나 올라갈 파일에서 key 처럼 보이는 문자열을 찾는다. (파일명만 돌려준다)

    추적 중인 파일 + 아직 add 하지 않았지만 .gitignore 에 걸리지 않는 파일을 본다.
    """
    try:
        r = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30)
        files = [f for f in r.stdout.split("\0") if f]
    except Exception:
        return []
    hits = []
    for f in files:
        p = ROOT / f
        try:
            if p.stat().st_size > 5_000_000:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if any(pat.search(text) for pat in _KEY_PATTERNS):
            hits.append(f)
    return hits
