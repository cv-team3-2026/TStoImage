"""main.ipynb 를 만든다. 노트북을 바꿀 때는 이 파일을 고친 뒤 실행한다: python tools/make_notebook.py"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/cv-team3-2026/TStoImage.git"

CELLS: list[tuple[str, str]] = [
    ("md", """# ts2img: time series chart 실험

- **A (Colab) 또는 B (서버) 중 하나만** 실행한 뒤 1번부터 진행합니다.
- `%ts2img <명령>` 은 터미널의 `python -m ts2img <명령>` 과 같습니다.
- 끊겨도 같은 명령을 다시 실행하면 끝난 문항은 건너뛰고 이어서 돕니다.
- API key 는 셀에 적지 않습니다. `secrets.env` 또는 Colab Secrets(열쇠 아이콘)에 넣습니다."""),

    ("md", """## A. Colab 준비

런타임 유형은 T4 GPU. 결과는 Google Drive(`MyDrive/ts2img_results`)에 2분마다 복사되고, 다음 세션에서 자동으로 복원됩니다.
런타임이 꺼지면 이 섹션을 다시 실행한 뒤 같은 `run` 명령을 실행하세요."""),
    ("code", f"""import os, sys
if not os.path.isdir("/content/TStoImage"):
    !git clone -q {REPO_URL} /content/TStoImage
%cd /content/TStoImage
!"{{sys.executable}}" -m pip install -q -r requirements.txt"""),
    ("code", """from ts2img import notebook as nb
nb.setup(drive=True)"""),
    ("code", "%ts2img doctor"),

    ("md", """## B. 서버 준비

README 대로 clone, venv, `pip install` 을 마치고, 그 venv 를 kernel 로 이 노트북을 엽니다.
터미널이 편하면 노트북 없이 README 의 CLI 를 쓰면 됩니다. `--background` 로 실행하면 SSH 가 끊겨도 계속 돕니다."""),
    ("code", """from ts2img import notebook as nb
nb.setup()"""),
    ("code", "%ts2img doctor"),

    ("md", """## 1. 실험 실행

실험 = `configs/experiments/<이름>.yaml`. 새 chart 를 넣었다면 부록에서 그림을 먼저 확인하세요.

| 옵션 | 뜻 |
| --- | --- |
| `--auto-serve` | 로컬 vLLM 을 띄우고 끝나면 끈다 (처음에는 설치 포함 약 10분) |
| `--background` | 셀/SSH 가 끊겨도 계속 돈다. Colab 런타임이 꺼지면 같이 꺼진다 |
| `--limit N` | task 마다 앞에서 N 문항만 |
| `--models a,b` | yaml 의 모델 대신 (`configs/models.yaml` 의 key) |
| `--benchmarks x` | 대상 task 만 바꿔서. 예: `tsrbench/perception/anomaly_detection` |
| `--modalities x` | `text`, `vision`, `text+vision` 중 쉼표로 |
| `--repeats N` | 같은 설정 반복 횟수 |
| `--dry-run` | 실행하지 않고 남은 문항만 보여 준다 |

`smoke` 는 가짜 모델로 몇 초 만에 끝나는 설치 확인용입니다."""),
    ("code", """EXP = "smoke"    # perception_baseline | perception_augment | tsrbench_full_baseline"""),
    ("code", """%ts2img run $EXP

# 예시
# %ts2img run perception_baseline --limit 20 --repeats 1 --auto-serve
# %ts2img run perception_augment --auto-serve --background
# %ts2img run perception_augment --models qwen3-vl-2b --modalities vision --auto-serve
# %ts2img run tsrbench_full_baseline --limit 20 --dry-run"""),

    ("md", "## 2. 진행 확인 / 중지"),
    ("code", """%ts2img status $EXP
# %ts2img status $EXP --watch    # 끝날 때까지 갱신
# %ts2img stop $EXP              # 중지. 다시 run 하면 이어서 돈다"""),

    ("md", """## 3. 결과 보기

실행 중에도 만들 수 있습니다. `run` 에 `--limit`, `--models` 등을 줬다면 `report` 에도 같은 옵션을 주세요.
파일 위치: `results/reports/<실험>/report.html`"""),
    ("code", """%ts2img report $EXP
nb.show_report(EXP)"""),
    ("code", """nb.download_results("reports")    # Colab: 보고서 zip 다운로드. "all" 이면 raw 결과까지"""),

    ("md", """## 부록. chart / prompt 미리보기 (선택)

모델을 부르지 않고 그림과 최종 입력만 확인합니다. chart 종류와 옵션: `%ts2img list`"""),
    ("code", """nb.show_charts(exp=EXP, n=3)
# nb.show_charts(["tsrbench_baseline", {"use": "line_style", "linewidth": 4}], task="tsrbench/perception/anomaly_detection", n=4)"""),
    ("code", """nb.show_prompt(task="tsrbench/perception", modality="vision")
# nb.show_prompt(exp=EXP)"""),
]


def build() -> dict:
    cells = []
    for kind, src in CELLS:
        lines = src.split("\n")
        source = [ln + "\n" for ln in lines[:-1]] + [lines[-1]]
        if kind == "md":
            cells.append({"cell_type": "markdown", "metadata": {}, "source": source})
        else:
            cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source})
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "colab": {"provenance": []},
            "accelerator": "GPU",
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


if __name__ == "__main__":
    out = ROOT / "main.ipynb"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")
