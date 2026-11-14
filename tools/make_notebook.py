"""main.ipynb 를 만든다. 노트북 구성을 바꿀 때는 이 파일을 고친 뒤 실행한다: python tools/make_notebook.py

(.ipynb 는 JSON 이라 직접 고치면 diff 를 읽기 어렵다. 셀 내용을 여기서 관리한다.)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/cv-team3-2026/TStoImage.git"

CELLS: list[tuple[str, str]] = [
    ("md", """# ts2img: time series chart 실험

line chart 를 어떻게 그려 주면 VLM 이 시계열 문제를 더 잘 푸는지 실험하는 노트북입니다.

- 위에서부터 차례로 실행합니다.
- 각 셀의 **첫 줄이 기본값**입니다. `#` 로 막아 둔 줄은 다른 선택지이니, 쓰고 싶은 줄의 `#` 를 지우고 실행하세요.
- `%ts2img <명령>` 은 터미널의 `python -m ts2img <명령>` 과 같습니다.
- **API key 는 셀에 적지 않습니다.** `secrets.env` 파일이나 Colab 의 Secrets(왼쪽 열쇠 아이콘)에 넣습니다. 자세한 내용은 README.
- 실행 중 끊겨도 같은 셀을 다시 실행하면 끝난 문항은 건너뛰고 이어서 돕니다."""),

    ("md", "## 0. 준비"),
    ("code", f"""# Colab 에서 이 노트북만 열었다면 코드를 먼저 받는다 (로컬/서버에서는 건너뛴다)
import os, sys

# (선택) GitHub 에 push 하지 않은 코드로 시험할 때만 True. 평소에는 그대로 둔다.
# 로컬에서 `python tools/pack_source.py` 로 만든 ts2img_src.tar.gz 를 아래 둘 중 한 곳에 올려 두고 쓴다 (README 참고).
#   - Colab 파일 창의 /content (Drive 연결이 필요 없다. 세션이 끝나면 지워진다)
#   - Google Drive 의 "내 드라이브" (세션이 끝나도 남는다)
USE_ARCHIVE = False

if "google.colab" in sys.modules:
    if USE_ARCHIVE:
        archive = "/content/ts2img_src.tar.gz"
        if not os.path.isfile(archive):     # /content 에 없으면 Drive 에서 찾는다
            from google.colab import drive
            drive.mount("/content/drive")   # 오류가 나면: Colab 에 로그인한 것과 같은 Google 계정을 고르고 권한을 모두 허용한다
            archive = "/content/drive/MyDrive/ts2img_src.tar.gz"
        assert os.path.isfile(archive), f"압축 파일이 없습니다: {{archive}}"
        print("코드를 푸는 파일:", archive)
        # 실행할 때마다 코드를 새로 푼다. 예전 코드 파일이 남지 않게 먼저 지운다 (results/, data/ 는 그대로).
        !mkdir -p /content/TStoImage && cd /content/TStoImage && rm -rf ts2img configs tests tools
        !tar -xzf "$archive" -C /content/TStoImage
        %cd /content/TStoImage
    elif not os.path.isdir("ts2img"):
        !git clone -q {REPO_URL} /content/TStoImage
        %cd /content/TStoImage

# 패키지 설치. 이미 있으면 금방 끝난다.
# Colab 에서 dependency conflict 경고가 떠도 실험에는 영향이 없다 (실험은 별도 프로세스에서 돈다).
!"{{sys.executable}}" -m pip install -q -r requirements.txt"""),
    ("code", """from ts2img import notebook as nb

nb.setup()
# nb.setup(drive=True)    # Colab: 결과를 Google Drive 에 보관한다 (세션이 끊겨도 남고, 다음에 이어서 돈다)"""),

    ("md", "## 1. 환경 확인\n\n컴퓨터 사양과 설정 상태를 확인합니다. 사양은 실험 결과 폴더에도 자동으로 기록됩니다."),
    ("code", "%ts2img sysinfo"),
    ("code", """%ts2img doctor
# %ts2img doctor --ping     # 모델 서버 / API 에 실제로 연결해 본다
# %ts2img list              # 쓸 수 있는 task, chart, model, 실험 목록"""),

    ("md", """## 2. chart 미리보기

모델을 부르지 않고 chart 만 그려 봅니다. 행이 chart 종류, 열이 문항입니다.
chart 종류와 옵션은 `%ts2img list` 또는 `ts2img/charts/README.md` 를 보세요."""),
    ("code", """nb.show_charts(exp="perception_augment", n=3)     # 실험 yaml 에 적힌 chart 전부
# nb.show_charts(["tsrbench_baseline", {"use": "line_style", "linewidth": 4}], task="tsrbench/perception/anomaly_detection", n=4)
# nb.show_charts(["tsrbench_baseline", {"use": "moving_average", "window": 8}], examples=True)    # augmentation_examples 의 9개
# nb.show_charts(exp="perception_augment", task="tsrbench/reasoning/causal", n=2)                 # 다른 task 에 적용하면"""),

    ("md", "## 3. prompt 미리보기\n\n모델에 실제로 들어가는 최종 입력(text 전문, 이미지, 요청 옵션)을 모델 호출 없이 확인합니다."),
    ("code", """nb.show_prompt(task="tsrbench/perception", modality="vision")
# nb.show_prompt(task="tsrbench/perception", modality="text+vision")
# nb.show_prompt(task="tsrbench/perception", modality="text")
# nb.show_prompt(task="tsrbench/perception/similarity_analysis", modality="vision", chart={"use": "multi_view", "views": ["full", "diff"]}, pos=3)
# nb.show_prompt(exp="perception_augment")     # 실험 yaml 의 설정 그대로"""),

    ("md", """## 4. 로컬 VLM 서버 (GPU 가 있을 때만)

- 외부 서버 URL 이나 유료 API 만 쓴다면 이 단계는 건너뜁니다.
- 5번에서 `--auto-serve` 를 쓰면 서버를 자동으로 띄우고 끝나면 끄므로 이 단계가 필요 없습니다. 서버를 계속 띄워 두고 여러 실험을 돌릴 때만 여기서 직접 띄웁니다.
- 모델 설정(양자화, dtype 등)은 `configs/models.yaml` 에 있습니다."""),
    ("code", "%ts2img serve setup      # vLLM 설치. 처음 한 번만, 몇 분 걸린다"),
    ("code", """%ts2img serve start qwen3-vl-4b
# %ts2img serve start qwen3-vl-2b
# %ts2img serve start qwen3-vl-8b
# %ts2img serve start qwen3-vl-4b --dry-run     # 실행될 명령만 확인
# %ts2img serve status
# %ts2img serve stop"""),

    ("md", """## 5. 실험 실행

실험 설정은 `configs/experiments/<이름>.yaml` 에 있습니다. 새 실험은 그 폴더의 파일을 복사해 고치면 됩니다."""),
    ("code", """EXP = "smoke"                      # 설치 확인용 (가짜 모델, 수 초)
# EXP = "perception_baseline"      # 1단계: 기준 성능 + 같은 설정 반복 시 흔들림
# EXP = "perception_augment"       # 2단계: chart 변형 비교
# EXP = "tsrbench_full_baseline"   # TSRBench 15개 task 전체"""),
    ("code", "%ts2img run $EXP --dry-run     # 계획만 확인: 어떤 조합이 몇 문항 남았는지"),
    ("code", """%ts2img run $EXP
# %ts2img run $EXP --auto-serve                  # 로컬 VLM 을 자동으로 띄우고 끝나면 끈다
# %ts2img run $EXP --auto-serve --background     # 셀이나 브라우저를 닫아도 계속 돈다 (아래 status 로 확인)
# %ts2img run $EXP --limit 20                    # task 마다 20문항만 (빠른 확인)
# %ts2img run $EXP --models qwen3-vl-2b          # yaml 을 고치지 않고 모델만 바꿔서
# %ts2img estimate $EXP                          # 유료 API: 몇 문항 보내 보고 전체 비용 추정
# %ts2img run $EXP --budget-usd 5                # 유료 API: 지출 상한 (유료 모델이면 필수)"""),
    ("code", """%ts2img status $EXP
# %ts2img status $EXP --watch     # 끝날 때까지 10초마다 갱신
# %ts2img stop $EXP               # 중지. 다시 run 하면 이어서 돈다"""),

    ("md", """## 6. 보고서

실행 도중에도 만들 수 있습니다 (그때까지의 결과로 만들고 "미완료" 라고 표시합니다).
`run` 에 `--limit`, `--models` 같은 옵션을 줬다면 `report` 에도 같은 옵션을 주세요."""),
    ("code", """%ts2img report $EXP
nb.show_report(EXP)"""),

    ("md", """## 7. 결과 보관

- 결과는 `results/` 에 있습니다. Colab 은 세션이 끝나면 지워지므로 내려받거나 Drive 에 보관하세요.
- 보고서(`results/reports/`)만 GitHub 에 올리고, raw 결과는 올리지 않습니다 (.gitignore)."""),
    ("code", """nb.download_results("reports")    # 보고서만 zip 으로
# nb.download_results("all")      # raw 결과까지 전부
# %ts2img sync push               # Google Drive 로 지금 바로 복사 (setup(drive=True) 로 시작했을 때)"""),
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
