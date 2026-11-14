# TStoImage (ts2img)

시계열 문제를 VLM 에게 물을 때, **line chart 를 어떻게 그려 주면 더 잘 푸는지** 실험하는 도구입니다.
[TSRBench](https://github.com/tianyi-lab/TSRBench) 의 방식(데이터, prompt, 채점)을 기준으로 삼고 chart 만 바꿔 가며 비교합니다.

- 지금 범위: TSRBench 15개 task 전부 실행 가능. 우선은 perception 4개 task 로 실험합니다.
- AI 도구로 작업한다면 [AGENTS.md](AGENTS.md) 를 먼저 읽히세요. 결정 사항과 현재 상태가 정리돼 있습니다.

## 빠른 시작

### Colab

1. `main.ipynb` 를 Colab 에서 엽니다 (런타임 유형: T4 GPU). Cursor / VS Code 에서는 Google Colab extension 으로 연결할 수 있습니다.
2. 위에서부터 차례로 실행합니다. 첫 셀이 저장소를 받고 패키지를 설치합니다.

### 내 컴퓨터 / 연구실 서버

```bash
git clone https://github.com/cv-team3-2026/TStoImage.git
cd TStoImage
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m ts2img doctor            # 설정 점검
python -m ts2img run smoke         # 가짜 모델로 전체 흐름 확인 (수 초, GPU 불필요)
python -m ts2img report smoke      # results/reports/smoke/report.md
```

노트북(`main.ipynb`)의 `%ts2img <명령>` 은 터미널의 `python -m ts2img <명령>` 과 같습니다.

## 실험 순서

| 단계 | 명령 | 하는 일 |
| --- | --- | --- |
| 1 | `python -m ts2img preview charts --exp perception_augment` | chart 가 어떻게 그려지는지 확인 (모델 호출 없음) |
| 2 | `python -m ts2img preview prompt --task tsrbench/perception` | 모델에 들어갈 최종 입력 확인 (모델 호출 없음) |
| 3 | `python -m ts2img run perception_baseline --auto-serve` | 기준 성능 측정. `--auto-serve` 는 로컬 VLM 을 띄우고 끝나면 끕니다 |
| 4 | `python -m ts2img run perception_augment --auto-serve` | chart 변형 비교 |
| 5 | `python -m ts2img report perception_augment` | 보고서 생성 |

자주 쓰는 옵션

```bash
python -m ts2img run <실험> --background     # 창을 닫아도 계속 실행
python -m ts2img status <실험> --watch       # 진행률, 경과 시간, 남은 시간
python -m ts2img stop <실험>                 # 중지
python -m ts2img run <실험> --limit 20       # task 마다 20문항만
python -m ts2img run <실험> --models qwen3-vl-2b
python -m ts2img list                        # task, chart, model, 실험 목록
```

**끊겨도 괜찮습니다.** 문항 하나가 끝날 때마다 파일에 기록합니다. 같은 `run` 명령을 다시 실행하면 끝난 문항은 건너뛰고 이어서 돕니다.
**설정을 바꾸면 새 폴더에 저장됩니다.** 답에 영향을 주는 설정(모델, chart, 입력 조건, sampling 등)이 하나라도 다르면 다른 run 으로 취급하므로 결과가 섞이지 않습니다.

## 실험 설정

실험 하나 = `configs/experiments/` 의 yaml 파일 하나입니다. 기존 파일을 복사해 고치면 됩니다.

```yaml
benchmarks:
  - tsrbench/perception                     # 15개 task 중 선택. tsrbench 만 쓰면 전부
models: [qwen3-vl-4b]                       # configs/models.yaml 의 key
modalities: [vision, text+vision]           # text | vision | text+vision
charts:
  - tsrbench_baseline                       # 첫 항목이 비교 기준
  - {use: line_style, linewidth: 4}
  - {use: moving_average, window: 8}
  - {use: tsrbench_baseline, post: [sharpen]}
sampling: official                          # 공식 코드처럼 temperature 를 보내지 않음
repeats: 1
```

- task 이름: `tsrbench/perception`, `tsrbench/perception/anomaly_detection`, `tsrbench/reasoning`, `tsrbench/reasoning/causal` ... (`python -m ts2img list`)
- 기본값은 TSRBench 공식 코드를 따릅니다. 다른 점은 [CHANGES.md](ts2img/benchmarks/tsrbench/CHANGES.md) 에 적어 두었습니다.
- 새 chart 만들기: [ts2img/charts/README.md](ts2img/charts/README.md)

## 모델

`configs/models.yaml` 에 정의합니다. 세 종류 모두 같은 방식(OpenAI-compatible URL)으로 호출합니다.

| 종류 | 예 | 필요한 것 |
| --- | --- | --- |
| 직접 서빙 (vLLM) | `qwen3-vl-4b` (T4), `qwen3-vl-8b` (RTX 5090) | Linux + NVIDIA GPU. `run --auto-serve` 또는 `serve start <key>` |
| 외부 URL | `lab-vlm` | 서버 주소를 `secrets.env` 에 |
| 유료 API | 파일 안의 주석 예시 | API key, `configs/pricing.yaml` 의 단가, `run --budget-usd <상한>` |

유료 모델은 단가와 지출 상한이 없으면 실행되지 않습니다. `python -m ts2img estimate <실험>` 으로 예상 비용을 먼저 볼 수 있습니다.

## API key 관리 (꼭 읽어 주세요)

- key 는 **`secrets.env` 파일에만** 적습니다. `secrets.example.env` 를 복사해 이름을 `secrets.env` 로 바꾸고 값을 채우세요.
- `secrets.env` 는 `.gitignore` 에 들어 있어 GitHub 에 올라가지 않습니다.
- key 를 코드, yaml, 노트북 셀에 직접 적지 마세요. 노트북은 출력까지 저장되므로 특히 위험합니다.
- Colab 에서는 파일 대신 왼쪽 열쇠 아이콘(Secrets)에 같은 이름으로 넣어도 됩니다.
- 올리기 전에 `python -m ts2img doctor` 를 실행하면 key 처럼 보이는 문자열이 git 에 올라갈 파일(아직 `git add` 하지 않은 파일 포함)에 있는지 검사합니다.
- 실수로 올렸다면 지우는 것으로는 부족합니다. 해당 key 를 바로 폐기하고 새로 발급받으세요.

## 결과

```
results/
  runs/<benchmark>/<task>/<model>/<입력>/<chart>__<hash>/   run 하나 (설정 조합 하나)
      predictions.jsonl     문항별 raw 응답과 채점 결과
      config.json           이 run 의 설정 전체
      env.json              실행한 컴퓨터 사양, 패키지 버전
      chart_samples/        모델에 보낸 chart 이미지 예시
      request_samples.json  모델에 보낸 요청 전문 예시
  experiments/<실험>/       status.json, run.log (진행 상황과 로그)
  reports/<실험>/           report.md, report.html, summary.csv, figures/
```

- GitHub 에는 `results/reports/` 만 올립니다 (가짜 모델로 돌린 `smoke` 보고서는 제외). 나머지는 용량이 크고 다시 만들 수 있어 `.gitignore` 로 제외했습니다.
- 보고서의 정확도는 두 가지입니다. **정확도**는 답을 못 뽑은 응답을 오답으로 친 값이고, **공식 방식**은 TSRBench 채점처럼 그런 응답을 분모에서 뺀 값입니다.

## Colab 에서 주의할 점

- 세션이 끝나면 `results/` 가 지워집니다. 노트북 첫 부분에서 `nb.setup(drive=True)` 로 Google Drive 보관을 켜면 2분마다 복사하고, 다음 세션에서 이어서 돕니다.
- 무료 Colab 은 브라우저를 닫거나 오래 자리를 비우면 끊깁니다. `--background` 는 셀이 끊겨도 계속 돌게 해 주지만 런타임 자체가 꺼지는 것은 막지 못합니다. 긴 실험은 Drive 보관을 켜고 여러 번에 나눠 돌리거나 연구실 서버를 쓰세요.
- 연구실 서버에서는 `--background` 로 실행하면 SSH 가 끊겨도 계속 돕니다.

### push 하지 않은 코드를 Colab 에서 시험하기

노트북은 기본으로 GitHub 의 코드를 받습니다. 고친 코드를 올리기 전에 Colab 에서 먼저 돌려 보려면:

1. 로컬에서 `python tools/pack_source.py` 를 실행합니다. 저장소 폴더에 `ts2img_src.tar.gz` 가 생깁니다 (git 에 올라갈 파일만 담기고, 이 파일 자체는 git 에서 제외됩니다).
2. 그 파일을 둘 중 한 곳에 올립니다. 둘 다 있으면 `/content` 쪽을 씁니다.
   - Colab 파일 창(왼쪽 폴더 아이콘)의 `/content`: Drive 연결이 필요 없습니다. 세션이 끝나면 지워집니다.
   - Google Drive 의 "내 드라이브": 세션이 끝나도 남습니다.
3. Colab 에서 `main.ipynb` 첫 코드 셀의 `USE_ARCHIVE = False` 를 `True` 로 바꿔 실행합니다.

코드를 다시 고쳤으면 1, 2를 반복하고 첫 셀부터 다시 실행합니다. `results/` 는 지워지지 않습니다.

Drive 연결에서 `Credentials propagation unsuccessful` 오류가 나면, 인증 창에서 Colab 에 로그인한 것과 같은 Google 계정을 고르고 권한을 모두 허용했는지 확인하세요 (`nb.setup(drive=True)` 도 같습니다).

## 폴더 구조

```
main.ipynb              실행용 노트북
configs/
  experiments/          실험 설정
  models.yaml           모델 목록과 서빙 설정
  pricing.yaml          유료 모델 단가
ts2img/
  charts/               chart 그리는 코드. 파일 하나 = chart 하나
  benchmarks/           벤치마크별 데이터, prompt, 채점 (tsrbench/)
  methods/              모델에 묻는 방식 (single_turn = TSRBench 방식)
  models/               모델 호출, vLLM 서빙
  report/               통계와 보고서
  runner.py             실행기 (재개, 진행 표시)
tests/                  pytest
augmentation_examples/  chart 아이디어용 예시 시계열 9개
third_party/            TSRBench 공식 코드 (참고용, git 제외)
data/                   벤치마크 데이터 (자동 다운로드, git 제외)
```

## 테스트

```bash
python -m pytest            # 약 6분. 처음에는 데이터(130MB)를 받습니다
```

## References

- [TSRBench GitHub](https://github.com/tianyi-lab/TSRBench.git), [논문](https://arxiv.org/abs/2601.18744), [데이터](https://huggingface.co/datasets/umd-zhou-lab/TSRBench)
