"""비밀 값이 저장소에 올라가지 않게 하는 장치."""
import subprocess

import pytest

from ts2img import secrets
from ts2img.paths import ROOT


def test_env_file_parsing(tmp_path):
    p = tmp_path / "secrets.env"
    p.write_text('# comment\nA=1\nB = "two"\nEMPTY=\nbad line\nC=\'x=y\'\n', encoding="utf-8")
    assert secrets.load_env_file(p) == {"A": "1", "B": "two", "C": "x=y"}


def test_get_prefers_environment(monkeypatch):
    monkeypatch.setenv("TS2IMG_TEST_KEY", "from-env")
    assert secrets.get("TS2IMG_TEST_KEY") == "from-env"
    assert secrets.get("TS2IMG_TEST_NO_SUCH_KEY") is None
    assert secrets.get(None) is None


def test_mask_hides_value():
    v = "sk-" + "abcdefghijklmnopqrstuvwxyz"   # key 모양 문자열을 그대로 적으면 doctor 검사에 걸린다
    m = secrets.mask(v)
    assert v not in m and "abcdefgh" not in m
    assert secrets.mask(None) == "(없음)"


def _git_ok():
    try:
        return subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True).returncode == 0
    except OSError:
        return False


@pytest.mark.skipif(not _git_ok(), reason="git 저장소가 아님")
def test_gitignore_covers_secrets_and_bulky_folders():
    for rel in ("secrets.env", ".env", "data/tsrbench/x.jsonl", "results/runs/a/predictions.jsonl",
                "results/experiments/a/run.log", "third_party/TSRBench/README.md", ".venv/x"):
        assert secrets.git_ignored(ROOT / rel) is True, rel
    for rel in ("secrets.example.env", "configs/models.yaml", "results/reports/x/report.md", "third_party/README.md", "main.ipynb"):
        assert secrets.git_ignored(ROOT / rel) is False, rel


@pytest.mark.skipif(not _git_ok(), reason="git 저장소가 아님")
def test_gitignore_does_not_hide_source():
    """코드, 설정, 문서가 .gitignore 에 걸려 빠지면 안 된다 (Windows 는 대소문자를 구분하지 않는다)."""
    out = subprocess.run(["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--",
                          "ts2img", "configs", "tests", "tools"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    hidden = [f for f in out.splitlines() if "__pycache__" not in f and not f.endswith(".pyc")]
    assert hidden == []
    for rel in ("ts2img/benchmarks/tsrbench/adapter.py", "ts2img/benchmarks/tsrbench/CHANGES.md",
                "configs/experiments/tsrbench_full_baseline.yaml", "AGENTS.md", "README.md", "requirements.txt"):
        assert secrets.git_ignored(ROOT / rel) is False, rel


@pytest.mark.skipif(not _git_ok(), reason="git 저장소가 아님")
def test_no_key_like_strings_in_tracked_files():
    assert secrets.scan_tracked_files() == []


@pytest.mark.skipif(not _git_ok(), reason="git 저장소가 아님")
def test_scan_sees_files_not_yet_added():
    """아직 git add 하지 않은 파일도 검사한다 (올리기 전에 잡아야 한다)."""
    p = ROOT / "_ts2img_scan_test.txt"
    p.write_text("key = " + "sk-" + "a" * 30 + "\n", encoding="utf-8")   # 가짜 값. 이 파일에 key 모양 문자열을 그대로 적지 않는다
    try:
        assert secrets.scan_tracked_files() == [p.name]
    finally:
        p.unlink()


def test_example_file_has_no_values():
    assert secrets.load_env_file(ROOT / "secrets.example.env") == {}
