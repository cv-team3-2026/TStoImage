"""main.ipynb 에서 쓰는 도우미.

실험에 영향을 주는 작업(chart 그리기, 모델 호출)은 전부 `python -m ts2img ...` 하위 프로세스에서 돈다.
노트북 kernel 은 결과 파일을 보여 주기만 한다. Colab 에 미리 깔린 패키지 버전과 섞이지 않게 하기 위해서다.
이 파일은 matplotlib, numpy 를 import 하지 않는다.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from ts2img.paths import ROOT, reports_dir, results_dir


def in_colab() -> bool:
    return "google.colab" in sys.modules or bool(os.environ.get("COLAB_RELEASE_TAG"))


def run(args: str | list[str], quiet: bool = False) -> int:
    """`python -m ts2img <args>` 를 실행하고 출력을 그대로 보여 준다. 셀을 중지하면 하위 프로세스도 멈춘다."""
    import shlex

    if isinstance(args, str):
        # 줄 끝의 `# 설명` 은 버린다. Windows 경로의 `\` 를 지키려고 posix 모드는 쓰지 않는다
        argv = shlex.split(args, comments=True, posix=False)
        argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] and a[0] in "\"'" else a for a in argv]
    else:
        argv = [str(a) for a in args]
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "JPY_PARENT_PID": os.environ.get("JPY_PARENT_PID", "1")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "ts2img", *argv], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    try:
        for line in proc.stdout:
            if not quiet:
                print(line, end="")
        return proc.wait()
    except KeyboardInterrupt:
        # 실행기가 상태를 기록하고 끝낼 수 있게 먼저 SIGINT 를 보낸다
        try:
            proc.send_signal(signal.SIGINT if os.name != "nt" else signal.SIGTERM)
            proc.wait(timeout=30)
        except Exception:
            proc.kill()
        print("\n중지했습니다. 같은 명령을 다시 실행하면 이어서 돕니다.")
        return 130


def _register_magic() -> None:
    """`%ts2img run smoke` = 터미널의 `python -m ts2img run smoke`"""
    try:
        from IPython import get_ipython

        def ts2img(line):
            run(line)

        ip = get_ipython()
        if ip is not None:
            ip.register_magic_function(ts2img, magic_kind="line", magic_name="ts2img")
    except Exception:
        pass


def setup(drive: bool = False, drive_dir: str = "/content/drive/MyDrive/ts2img_results") -> None:
    """노트북 준비: `%ts2img` 명령 등록, Colab Secrets 읽기, (선택) Google Drive 보관."""
    from ts2img import secrets

    os.chdir(ROOT)
    _register_magic()
    found = secrets.export_colab_secrets()
    print(f"작업 폴더: {ROOT}")
    print("secrets: " + (", ".join(found) if found else "설정된 값 없음 (공개 모델을 직접 띄우는 경우 필요 없음)"))
    if drive:
        if not in_colab():
            print("Colab 이 아니어서 Drive 연결을 건너뜁니다. 결과는 results/ 에 그대로 남습니다.")
        else:
            from google.colab import drive as gdrive  # type: ignore

            gdrive.mount("/content/drive")
            os.environ["TS2IMG_SYNC_DIR"] = drive_dir
            run(["sync", "restore", "--dir", drive_dir])
            print(f"Drive 보관: {drive_dir} (실행 중 2분마다 복사, 이전 결과는 방금 복원함)")
    elif in_colab():
        print("주의: Colab 은 세션이 끝나면 results/ 가 지워집니다. 오래 돌릴 때는 setup(drive=True) 를 쓰세요.")
    print("준비 완료. 이제 `%ts2img <명령>` 을 쓸 수 있습니다. 예: %ts2img doctor")


def _chart_arg(c) -> str:
    import yaml

    return c if isinstance(c, str) else yaml.safe_dump(c, default_flow_style=True, allow_unicode=True, width=10_000).strip()


def show_charts(charts: list | None = None, task: str | None = None, n: int = 3, pos: list[int] | None = None,
                examples: bool = False, exp: str | None = None):
    """chart 를 문항별로 나란히 그려 보여 준다 (행 = chart, 열 = 문항). 모델은 부르지 않는다.

    charts:   예: ["tsrbench_baseline", {"use": "line_style", "linewidth": 4}]. 비우면 exp 의 charts
    task:     예: "tsrbench/perception/anomaly_detection"
    pos:      선택된 문항 중 몇 번째를 볼지 (0부터). 비우면 앞에서 n 개
    examples: True 면 augmentation_examples/ 의 예시 9개로 그린다
    exp:      실험 이름. 그 yaml 의 charts 와 대상 task 를 쓴다
    """
    from IPython.display import Image, display

    out = results_dir() / "preview" / "charts.png"
    args = ["preview", "charts", "--out", str(out), "--n", str(n)]
    if exp:
        args += ["--exp", exp]
    if task:
        args += ["--task", task]
    if examples:
        args += ["--examples"]
    if pos:
        args += ["--pos", *map(str, pos)]
    if charts:
        args += ["--charts", *[_chart_arg(c) for c in charts]]
    if run(args) == 0:
        display(Image(filename=str(out)))


def show_prompt(task: str | None = None, modality: str = "vision", chart=None, pos: int = 0,
                exp: str | None = None, model: str | None = None, max_chars: int = 6000):
    """모델에 실제로 들어가는 최종 요청(text 전문, 이미지, 요청 옵션)을 모델 호출 없이 보여 준다."""
    from IPython.display import Image, display

    out_dir = results_dir() / "preview"
    for old in out_dir.glob("prompt_image_*"):
        old.unlink()
    args = ["preview", "prompt", "--modality", modality, "--pos", str(pos), "--max-chars", str(max_chars)]
    if task:
        args += ["--task", task]
    if exp:
        args += ["--exp", exp]
    if model:
        args += ["--model", model]
    if chart:
        args += ["--charts", _chart_arg(chart)]
    if run(args) == 0:
        for p in sorted(out_dir.glob("prompt_image_*")):
            display(Image(filename=str(p)))


def show_report(name: str):
    """보고서를 노트북 안에 표시한다. 먼저 `%ts2img report <이름>` 으로 만들어 둔다."""
    from IPython.display import HTML, display

    path = reports_dir() / name / "report.html"
    if not path.is_file():
        print(f"보고서가 없습니다. 먼저 실행하세요: %ts2img report {name}")
        return
    display(HTML(path.read_text(encoding="utf-8")))


def download_results(what: str = "reports"):
    """결과를 zip 으로 묶는다. Colab 이면 브라우저로 내려받는다. what: "reports"(보고서만) | "all"(raw 결과 포함)"""
    src = reports_dir() if what == "reports" else results_dir()
    if not src.is_dir():
        print(f"폴더가 없습니다: {src}")
        return None
    zip_path = shutil.make_archive(str(ROOT / f"ts2img_{what}"), "zip", src)
    print(f"압축 완료: {zip_path} ({Path(zip_path).stat().st_size / 1e6:.1f} MB)")
    if in_colab():
        from google.colab import files  # type: ignore

        files.download(zip_path)
    return zip_path
