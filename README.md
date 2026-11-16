# TStoImage (ts2img)

시계열 문제를 VLM 에게 물을 때 **line chart 를 어떻게 그려 주면 더 잘 푸는지** 실험하는 도구입니다.
[TSRBench](https://github.com/tianyi-lab/TSRBench) 의 데이터, prompt, 채점을 기준으로 chart 만 바꿔 비교합니다.
AI 도구로 작업할 때는 [AGENTS.md](AGENTS.md) 를 먼저 읽히세요.

## Colab

1. `main.ipynb` 를 Colab 에서 엽니다 (런타임: T4 GPU).
2. **A. Colab 준비** 섹션을 실행한 뒤 1번(실험 실행)부터 진행합니다.

결과는 Google Drive(`MyDrive/ts2img_results`)에 2분마다 복사됩니다. 런타임이 꺼지면 A 섹션을 다시 실행하고 같은 `run` 명령을 실행하면 이어서 돕니다.
`--background` 는 셀이 끊겨도 계속 돌게 하지만 런타임 자체가 꺼지는 것은 막지 못합니다.

## 연구실 서버 (Linux + NVIDIA GPU)

```bash
git clone https://github.com/cv-team3-2026/TStoImage.git && cd TStoImage
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m ts2img run smoke                                          # 설치 확인 (가짜 모델, 수 초)
python -m ts2img run perception_baseline --auto-serve --background  # SSH 가 끊겨도 계속
python -m ts2img status perception_baseline --watch
python -m ts2img stop perception_baseline                           # 다시 run 하면 이어서
python -m ts2img report perception_baseline
```

`--auto-serve` 는 vLLM 을 별도 venv 에 설치하고(처음 한 번) 모델을 띄운 뒤 끝나면 끕니다. 노트북을 쓰려면 같은 venv 를 kernel 로 `main.ipynb` 의 **B. 서버 준비** 부터 실행합니다.
아직 확인하지 못한 것: Linux 에서의 `stop`, `qwen3-vl-8b` 서빙.

자주 쓰는 옵션: `--limit N` (task 마다 N 문항), `--models a,b`, `--benchmarks`, `--modalities`, `--repeats`, `--dry-run`. 전체 목록은 `python -m ts2img run --help`, 쓸 수 있는 task/chart/model/실험은 `python -m ts2img list`.

## 결과 보기

`python -m ts2img report <실험>` 이 `results/reports/<실험>/` 에 `report.html`, `report.md`, `summary.csv` 를 만듭니다. `run` 에 `--limit`, `--models` 등을 줬다면 `report` 에도 같은 옵션을 줍니다.

- **정확도**: 답을 못 뽑은 응답과 context 초과 문항을 오답으로 친 값.
- **공식 방식**: TSRBench 처럼 읽지 못한 응답을 분모에서 뺀 값. 이것만 인용하지 않습니다.

```
results/
  runs/<benchmark>/<task>/<model>/<입력>/<chart>__<hash>/   설정 조합 하나 (predictions.jsonl, config.json, chart_samples/)
  experiments/<실험>/                                      status.json, run.log
  reports/<실험>/                                          보고서 (git 에는 이것만 올린다)
```

같은 명령을 다시 실행하면 끝난 문항은 건너뜁니다. 답에 영향을 주는 설정(모델, chart, 입력 조건, sampling 등)이 바뀌면 새 폴더에 저장되므로 결과가 섞이지 않습니다.

## 실험 설정

실험 하나 = `configs/experiments/<이름>.yaml`. 기존 파일을 복사해 고칩니다.

```yaml
benchmarks: [tsrbench/perception]            # tsrbench 만 쓰면 15개 task 전부
models: [qwen3-vl-4b]                        # configs/models.yaml 의 key
modalities: [vision, text+vision]            # text | vision | text+vision
charts:
  - tsrbench_baseline                        # 첫 항목이 비교 기준
  - {use: line_style, linewidth: 4}
  - {use: tsrbench_baseline, post: [sharpen]}
sampling: official                           # official | deterministic | {temperature: ..., seed: ...}
repeats: 1
```

생략하면 쓰는 기본값 (공식 TSRBench 방식, 다른 점은 [CHANGES.md](ts2img/benchmarks/tsrbench/CHANGES.md)):
`max_tokens: null` (보내지 않음), `response_format: json_schema`, `answer_retries: 10`, `request_timeout: 1800`, `text_stride: 1`, `ts_placeholder: keep`, `concurrency: 8`, `limit: null`.
너무 느리면 `max_tokens` 와 `answer_retries` 를 줄입니다. 새 chart 만들기: [ts2img/charts/README.md](ts2img/charts/README.md)

## 모델

`configs/models.yaml` 에 정의합니다. 모두 OpenAI-compatible URL 로 호출합니다.

- **직접 서빙 (vLLM)**: `serve` 블록이 있는 모델. `qwen3-vl-4b` (T4 기본), `qwen3-vl-2b`, `qwen3-vl-8b` (RTX 5090).
- **외부 URL**: `base_url` 또는 `base_url_env` + `api_key_env`. 예: `lab-vlm`. 상용 API 도 같은 방식이며 지출 상한 기능은 없습니다.

`max_model_len` (context 한도): perception 은 8192, 15개 task 를 vision 만으로 돌리면 16384, text 가 들어가면 32768 이상이 필요합니다. 넘는 문항은 `context_overflow` 로 기록되고 오답으로 집계됩니다. 한도를 올려 다시 실행하면 그 문항만 다시 돕니다. 한 실험 도중에는 바꾸지 않습니다.

## API key

- key 는 `secrets.env` 에만 적습니다 (`secrets.example.env` 를 복사). git 에 올라가지 않습니다. Colab 에서는 Secrets(열쇠 아이콘)에 같은 이름으로 넣어도 됩니다.
- 코드, yaml, 노트북 셀에 적지 않습니다. 올리기 전에 `python -m ts2img doctor` 로 검사합니다.
- 실수로 올렸다면 바로 폐기하고 새로 발급받습니다.

## 폴더와 테스트

`configs/` 설정, `ts2img/` 코드 (`charts/`, `benchmarks/`, `methods/`, `models/`, `report/`, `runner.py`), `tests/`, `augmentation_examples/` chart 아이디어용 예시, `third_party/` 공식 코드 (git 제외).
테스트: `python -m pytest` (약 6분, 처음에 데이터 130MB 를 받습니다).

## References

[TSRBench GitHub](https://github.com/tianyi-lab/TSRBench.git), [논문](https://arxiv.org/abs/2601.18744), [데이터](https://huggingface.co/datasets/umd-zhou-lab/TSRBench)
