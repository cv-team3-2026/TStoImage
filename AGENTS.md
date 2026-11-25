# AGENTS.md

이 저장소에서 AI 도구(Cursor 등)로 작업할 때 먼저 읽는 문서입니다. 사람이 읽어도 됩니다.
프로젝트의 목표, 지금까지의 결정과 그 이유, 지켜야 할 규칙, 현재 상태를 적습니다.

**이 문서는 고정된 규칙집이 아닙니다.** 작업하면서 사실이 바뀌면 고치세요. 고치는 방법은 맨 아래 "이 문서 고치기" 에 있습니다.

## 1. 프로젝트

- KNU computer vision 수업 팀 프로젝트 (cv-team3-2026). 팀원 중에는 코딩 경험이 적은 사람도 있다.
- 질문: 시계열 문제를 VLM 에게 물을 때 **line chart 를 어떻게 그려 주면 성능이 달라지는가**.
  (표와 chart 를 같이 주면 표만 줄 때보다 낫다는 것은 알려져 있다. 여기서는 chart 를 바꾸는 효과를 본다.)
- 해 볼 chart 변형: 선 굵기와 색, 해상도, sharpening, legend, 이동평균 추세선, 변환한 그림 여러 장 등.
- 기준: TSRBench (arXiv 2601.18744) 의 데이터, prompt, 채점 방식.
- 범위: 15개 task 전부 구현돼 있다. 실험은 perception 4개 task 부터 하고, 시간이 되면 넓힌다.
- 나중에 해 볼 수 있는 것: 다른 벤치마크, 자체 데이터셋, plotting tool 을 쓰는 agent 방식 (`ts2img/methods/` 가 확장 지점).

## 2. 구조 한눈에

```
실험 yaml (configs/experiments)
   -> cell 로 전개: (benchmark unit) x (model) x (입력 조건) x (chart) x (반복)
   -> cell 하나 = run 폴더 하나: results/runs/<bench>/<unit>/<model>/<입력>/<chart>__<hash8>[__rN]/
   -> 문항마다 predictions.jsonl 에 한 줄씩 기록
   -> report 가 run 폴더들을 읽어 results/reports/<실험>/ 을 만든다
```

| 위치 | 역할 |
| --- | --- |
| `ts2img/config.py` | yaml 로더, cell 전개, run hash |
| `ts2img/runner.py` | 실행, 재개, 진행 표시, status.json |
| `ts2img/benchmarks/tsrbench/` | 데이터, 공식 prompt, 채점. 공식과 다른 점은 `CHANGES.md` |
| `ts2img/charts/` | 파일 하나 = chart 하나. `render(sample, **params)` |
| `ts2img/methods/` | 모델에 묻는 방식. `single_turn` = TSRBench 방식 |
| `ts2img/models/` | OpenAI-compatible client, vLLM 서빙 |
| `ts2img/report/` | 통계(Wilson CI, McNemar, Holm), report.md / html / csv |
| `ts2img/notebook.py`, `main.ipynb` | 노트북용 얇은 껍데기. 실제 일은 CLI 가 한다 |
| `tools/make_notebook.py` | `main.ipynb` 를 만드는 script |

명령 목록은 `python -m ts2img --help`, 사용법은 `README.md`.

## 3. 확인된 사실

직접 확인한 것만 적는다. 추측은 5번 "확인하지 못한 것" 에 둔다.

TSRBench

- 공식 코드: `tianyi-lab/TSRBench` commit `084e3f0` (`third_party/TSRBench`, git 제외).
- 공개 데이터: HuggingFace `umd-zhou-lab/TSRBench`, revision `de20bef327be628cb79fc8f93965ba904470f3fc`. 공식 `download_data.py` 가 가리키는 `ParadiseYu/TSRBench` 는 접근이 안 된다.
- 파일 12개, task 15개, 4,125문항. perception 700 = pattern 371 + anomaly 129 + similarity 113 + noise 87.
- perception 은 다른 task 와 형식이 다르다: `choices`, `name_of_series` 가 없고 선택지가 질문 본문에 있으며, 본문에 `<ts><ts/>` 표기와 "You must start response from A)..." 문구가 남아 있다.
- 공식 chart 는 이름 없는 series 를 `series_0` 으로 적는다. perception 질문은 "time series 1" 이라고 부른다 (불일치. chart 옵션 `names` 로 실험 가능).
- 공식 코드는 sampling 값을 보내지 않는다 (서버 기본값). 채점은 `eval()` 을 쓰고 읽지 못한 응답을 분모에서 뺀다.
- event_prediction 은 정답 360개 중 303개가 B 다. 그래서 보고서에 "최빈 정답만 찍었을 때" 기준선을 같이 싣는다.
- 문항 길이: text 조건에서 qualitative_decision 은 문항당 숫자 12,000개(약 7만 자), causal 은 약 3만 자. vision 만 써도 abductive, time_series_forecasting 은 질문 글이 길다(최대 약 3만 자). README "모델" 절의 `max_model_len` 설명 참고.

모델

- `Qwen/Qwen3-VL-3B-Instruct` 는 없다. 2B / 4B / 8B / 32B 가 있다. T4 기본값은 4B.
- 공식 실험은 Qwen3-VL 8B, 32B 를 GPU 4장으로 돌렸다. 4B 결과는 논문 수치와 직접 비교할 수 없다.

이 저장소에서 검증한 것 (Windows, GPU 없음, `python -m pytest`)

- 4,125문항 전부에 대해 로더, 세 입력 조건의 prompt, 공식 chart 렌더링이 오류 없이 동작한다.
- 공식 chart 는 `augmentation_examples/*/baseline.png` 과 크기가 같고 내용이 일치한다.
- 가짜 OpenAI-compatible 서버로 요청 형식, 재개, 강제 종료 후 이어 돌기, 설정 변경 시 새 폴더, context 초과, 인증 실패, 지출 상한, 백그라운드 실행과 중지, 보고서 생성을 확인했다.

Colab 에서 확인한 것 (2026-11-13, GPU 런타임, `run smoke --models qwen3-vl-4b --auto-serve`, 112건. 출력은 노트북 셀에서만 봤고 raw 결과는 보지 못했다)

- `requirements.txt` 고정 버전이 설치된다. Colab 기본 패키지(`datasets`, `gradio`, `numba`, `bigframes`)와 dependency conflict 경고가 뜨지만 이 저장소는 그 패키지를 쓰지 않는다.
- Drive 연결이 동작한다. Drive 인증은 Colab 에 로그인한 계정과 다른 계정을 고르면 `Credentials propagation unsuccessful` 로 실패한다.
- `vllm==0.33.0` 이 별도 venv 에 설치되고, `serve.py` 가 만든 flag 로 `qwen3-vl-4b` (float16, `max_model_len` 8192) 서버가 뜬다. 처음 실행은 설치 약 2분 + 서버 준비 약 8분(모델 다운로드 포함).
- 112건이 오류 0, context 초과 0 으로 끝났다. 답을 못 뽑은 응답은 2건(둘 다 causal).
- 속도: perception 56건 약 13분, causal 56건 약 81분 (concurrency 8, Tesla T4).
- vision 조건은 응답이 길다: 요청당 출력 약 1,000 token, 응답 시간 중앙값 54~86초. 16문항 중 3~5건이 `max_tokens` 2048 (당시 기본값) 에서 잘렸고 5~6건이 재요청됐다. 잘린 것은 모두 causal 이다.
- 잘린 응답은 반복 생성이 아니라 선택지를 계속 재검토하며 끝나지 않는 풀이였다. 끝까지 쓴 응답은 약 800 token 에서 답을 낸다. JSON 형식 강제(`json_schema`)는 동작한다.
- 이때의 causal vision 정확도는 믿을 수 없다. 잘린 풀이 본문의 글자를 답으로 집는 채점 오류가 있었다 (adapter version 2 에서 수정).
- text+vision 조건은 출력이 11~12 token 이다. 공식 schema 가 `answer` 만 필수라서(vision, text 는 `reasoning` 도 필수) 모델이 풀이를 쓰지 않는다. 그래서 **vision 과 text+vision 의 차이에는 "풀이를 쓰느냐" 가 섞여 있다.** 같은 입력 조건 안의 chart 비교에는 영향이 없다.
- 서버 기본 sampling 은 temperature 0.7, top_p 0.8, top_k 20 이다 (`sampling: official` 일 때 쓰이는 값).
- `sync push` 로 Drive 에 결과가 복사된다 (파일 347개).
- 8문항짜리 결과라 정확도 숫자는 논문과 비교할 수 없다 (95% 신뢰구간 폭이 약 ±30%p).

## 4. 결정 사항과 이유

| 날짜 | 결정 | 이유 |
| --- | --- | --- |
| 2026-11-12 | 모든 모델을 OpenAI-compatible URL 로 호출 | 직접 서빙, 외부 서버, 유료 API 를 한 경로로 다루려고. 공식 코드도 같은 방식 |
| 2026-11-12 | run 폴더 이름에 설정 hash. hash 에는 "같은 문항에 같은 답이 나오는 조건"만 넣는다 | 설정이 바뀌면 자동으로 새 폴더가 되고, 문항 수(`limit`)나 하위 task 선택만 바꾸면 같은 폴더를 이어 쓴다 |
| 2026-11-12 | hash 에 넣지 않는 것: `limit`, 하위 task 선택, `concurrency`, port, GPU 번호, `max_model_len` | 답을 바꾸지 않는 값. `max_model_len` 을 넘는 문항은 `context_overflow` 로 따로 기록하고, 한도를 올리면 그 문항만 다시 돈다 |
| 2026-11-12 | 기본 sampling 은 `official` (아무것도 보내지 않음) + `repeats` 로 반복 | 논문 방식을 따르되, 같은 설정에서도 결과가 흔들리므로 그 크기를 먼저 잰다. chart 효과가 그보다 작으면 효과라고 말할 수 없다 |
| 2026-11-12 | 정확도를 두 가지로 보고 (답 없음 = 오답 / 공식 방식) | 공식 채점은 읽지 못한 응답을 빼서 정확도가 높게 나올 수 있다 |
| 2026-11-12 | context 초과 문항은 오답으로 집계 | 못 푼 문항이 빠지면 text 조건이 유리해 보인다 |
| 2026-11-12 | `max_tokens` 기본 2048 (공식은 없음) | JSON 형식을 강제하면 끝없이 생성하는 경우가 있어 한 문항이 실험을 멈출 수 있다 |
| 2026-11-12 | chart 비교는 같은 문항끼리 (McNemar, 여러 비교는 Holm 보정) | 700문항으로는 몇 %p 차이를 구분하기 어렵다. 문항 단위 비교가 가장 민감하다 |
| 2026-11-12 | API key 는 `secrets.env` (git 제외) 또는 Colab Secrets. yaml 에는 이름만 | 코딩 경험이 적은 팀원이 key 를 올리는 사고를 막으려고 |
| 2026-11-12 | 유료 모델은 단가(`pricing.yaml`)와 `--budget-usd` 가 없으면 실행 안 됨. 단가는 미리 채우지 않음 | 예상 못 한 지출 방지. 단가는 자주 바뀌므로 쓰는 사람이 확인해 넣는다 |
| 2026-11-12 | vLLM 은 별도 venv (`serve setup`) | 실험 환경의 패키지 버전(matplotlib 등)을 고정하기 위해 |
| 2026-11-12 | 노트북은 CLI 를 하위 프로세스로 부른다 (`%ts2img`) | Colab 에 미리 깔린 패키지와 섞이지 않게. 터미널과 노트북의 명령이 같아진다 |
| 2026-11-12 | `results/` 는 `reports/` 만 git 에 올린다 | raw 결과는 크고(응답 전문 포함) 다시 만들 수 있다 |
| 2026-11-12 | 공식 코드는 `third_party/` 에 두고 고치지 않는다 | 원본과 대조할 수 있게. 다른 점은 `CHANGES.md` 에 기록 |
| 2026-11-13 | `max_tokens` 기본값을 "보내지 않음" 으로 (2026-11-12 의 2048 결정을 바꿈). 재요청 10회, text+vision schema 도 공식 그대로 둔다 | 사용자 결정: 공식 benchmark 기준을 따른다. 2048 에서는 causal 응답의 절반 이상이 잘렸다. 대가는 시간이다 (끝나지 않는 풀이는 context 한도까지 생성하고 재요청된다). 느리면 실험 yaml 에서 `max_tokens`, `answer_retries` 를 줄인다 |
| 2026-11-13 | `max_model_len` 은 계속 hash 에 넣지 않는다. 대신 한 실험을 도는 동안에는 바꾸지 않는다 | `max_tokens` 를 보내지 않으면 `max_model_len` 이 출력 상한도 정한다. 도중에 바꾸면 길이 한도에서 잘린 응답만 조건이 달라진 채 같은 폴더에 남는다 |
| 2026-11-13 | push 전 코드는 압축 파일로 Colab 에 옮겨 시험한다 (`tools/pack_source.py` + 첫 셀 `USE_ARCHIVE`) | 팀 공용 저장소라 검증하지 않은 코드를 먼저 올리고 싶지 않아서. 기본값은 그대로 GitHub clone |
| 2026-11-14 | `pack_source.py` 와 `USE_ARCHIVE` 삭제 (2026-11-13 결정을 바꿈) | 사용자가 개인 branch 로 해결했다. 필요하면 직접 branch 를 clone 한다 |
| 2026-11-14 | 유료 API 비용 기능 삭제: `paid`, `pricing.yaml`, `estimate`, `--budget-usd` (2026-11-12 결정을 바꿈) | 한 번도 쓰지 않았고 구조만 복잡하게 했다. 상용 API 는 외부 URL 로 계속 호출할 수 있다. 대가: 지출 상한이 없으니 `--limit` 으로 직접 줄인다 |
| 2026-11-14 | 노트북 구조: A. Colab 준비 / B. 서버 준비 중 하나 실행 후 공통 실행, 진행, 결과. 미리보기는 부록. 출력 없이 commit | 환경별 차이는 준비 단계뿐이다. 실행 셀을 환경별로 두면 두 벌이 어긋난다 |
| 2026-11-14 | 설정 파일과 문서의 주석을 최소화. 설명은 README 한 곳에 | 같은 설명이 yaml, 노트북, 문서에 반복돼 읽기 어려웠다. Hydra 는 hash/재개 구조와 맞지 않아 쓰지 않는다 |
| 2026-11-25 | `applied_forecast`: metro, seoul bike, kpx 를 벤치마크 3개로 나눠 text 대 vision 만 비교. sampling 은 official. schema 는 reasoning+answer. 문항은 최근 168시간으로 다음 24시간 평균의 다섯 단계. KPX CSV 는 수동 (`ts2img/benchmarks/applied/README.md`) | 차트 스타일이 아니라 plot 대 text 를 실제 예측에서 본다. 데이터셋 점수는 합치지 않는다. answer 만 요구하면 풀이 유무가 비교에 섞인다. |
| 2026-11-25 | `applied_forecast` 창을 직전 4주(672시간)로 바꿈. 문항은 90개, 예측일 간격 2일. benchmark version 2, revision `next-day-level-v2`. 7일 실험 결과는 쓰지 않는다 | 7일에는 같은 요일이 한 번이라 반복이 보이지 않는다. 4주면 네 번 보인다. 교통량은 4주가 빈틈 없이 이어진 날이 196일이라 150개를 간격 2일로 채우지 못한다. 세 데이터의 간격을 같게 두려고 90으로 맞춘다. version 을 올려 이전 답과 섞이지 않게 한다. |
| 2026-11-25 | `applied_forecast_scale3`: 같은 문항을 vision 과 `line_style scale 3` 만으로 돌린다. 본 실험 yaml 은 공식 차트 그대로 | perception 에서 그림 3배 확대가 text+vision 에 +4.0%p 였다. 차트만 바꾼 비교라 문항 version 은 그대로 둔다. |
| 2026-11-25 | `applied_peak_hour`: 교통량만, 내일 피크 시각(0–23시)을 vision 으로 맞춘다. 직전 14일, 자정 세로선. 채점은 ±1시간. 90문항 | 24시간 평균은 하루 파도에 묻힌다. 7일 전 시각을 베끼면 54%이고, 최근 평일 봉우리의 오전·오후를 보면 67%까지다. 그 위는 1·2등 시각이 비슷해 정답이 흔들린다 |
| 2026-11-25 | `applied_seoul_peak`: 따릉이 재배치 피크(≥1000대/시) 시각 집합 F1. 7일+내일 기상예보, vision, `bike_peak` scale3 가로 2패널. 전환일 우선 60문항 | Metro는 계절 naive가 너무 높다. 날씨·휴일 전환에서 vision 우위를 보려 한다. perception 에서 이득이 있던 3배+가로 배치를 쓴다 |
| 2026-11-25 | `applied_seoul_peak_gemini`: 위와 동일 조건, 모델만 `gemini-hydrogen` (OpenAI-compatible Gemini API) | Qwen 4B vision 상한을 상용 모델과 비교한다 |
| 2026-11-25 | 대형 VLM 용 lab 실험 2개: `applied_seoul_peak_lab`, `applied_seoul_forecast_lab` (text/vision/text+vision, `lab-vlm`) | 다른 PC 에서 baseline 격파 여부를 본다. forecast 는 Seoul+scale3 이 4B 기준 가장 유망했다 |

## 5. 현재 상태

된 것: 위 구조 전체, TSRBench 15개 task, chart 6종 + sharpen 후처리, 실행/재개/보고서, 테스트.

**확인하지 못한 것** (GPU 와 Colab 이 없는 환경에서 만들었다. 처음 쓰는 사람이 확인하고 이 문서를 고쳐 주세요)

1. vLLM 서빙 중 `qwen3-vl-4b` 외의 preset (`qwen3-vl-2b`, `qwen3-vl-8b`), 연구실 서버, `extra_args`.
2. `max_tokens` 를 보내지 않을 때의 실제 동작과 속도 (응답이 context 한도까지 가는지, `request_timeout` 1800초 안에 끝나는지). context 초과 오류 문구가 `client.py` 의 `_OVERFLOW_HINTS` 에 걸리는지 (smoke 의 문항은 짧아서 초과가 나지 않았다).
3. Colab: Secrets 읽기, Drive 에서 복원(`nb.setup(drive=True)`)과 실행 중 자동 복사, `--background` 프로세스가 셀 종료 뒤에도 사는지.
4. Linux 에서의 `stop` (SIGINT 경로). Windows 에서만 확인했다.
5. 상용 API 호출. 한 번도 보내지 않았다.
6. 2026-11-14 에 다시 만든 `main.ipynb` (A/B 구조). Colab 에서 아직 돌려 보지 않았다.

다음 할 일

1. 새 기본값(`max_tokens` 없음, adapter version 2)으로 perception 만 짧게 돌려 속도와 잘림 건수를 확인한다: `run perception_baseline --limit 20 --repeats 1 --auto-serve`.
2. `perception_baseline` 실행. 반복 간 흔들림과 text / vision / text+vision 기준 성능 확인. smoke 의 속도(perception 분당 약 4건)로는 6,300건에 하루 이상 걸리므로 `--limit` 이나 `repeats` 를 줄이거나 연구실 서버를 쓴다.
3. `perception_augment` 실행, 보고서 검토, chart 아이디어 추가.
4. `applied_forecast` 실행. KPX CSV 는 `data/applied/kpx/hourly.csv`. 없으면 `--benchmarks applied_metro,applied_seoul`. 설명은 `ts2img/benchmarks/applied/README.md`.

## 6. 작업 규칙

코드

- 주석과 사용자에게 보이는 메시지는 **간결한 한국어**. 기술 용어(chart, prompt, sampling, task ...)는 영어 그대로 둔다.
- 새 chart 는 `ts2img/charts/<이름>.py` 하나로. 규칙은 `ts2img/charts/README.md`.
- **답이나 그림이 달라지게 코드를 고치면 version 을 올린다**: chart 는 모듈의 `VERSION`, 벤치마크는 class 의 `version`, method 는 모듈의 `VERSION`, hash 구성 자체는 `config.IDENTITY_VERSION`. 올리지 않으면 예전 결과와 새 결과가 같은 폴더에 섞인다.
- 실험 설정 항목을 추가할 때는 그것이 답에 영향을 주는지 판단해서 `Cell.identity()` 에 넣거나 뺀다. 기본값일 때 기존 hash 가 바뀌지 않게 한다 (`ts_placeholder` 처리 참고).
- TSRBench 공식 동작과 달라지는 변경은 `ts2img/benchmarks/tsrbench/CHANGES.md` 에 적는다. 기본값은 공식 동작을 따르고, 다른 동작은 옵션으로 둔다.
- `third_party/` 는 고치지 않는다.
- `requirements.txt` 의 `==` 고정 버전(matplotlib, pillow, numpy, openai)은 이유 없이 바꾸지 않는다. 그림이 달라지면 실험 조건이 달라진다.
- `main.ipynb` 는 직접 고치지 말고 `tools/make_notebook.py` 를 고친 뒤 실행한다. 노트북 셀에는 CLI 호출과 표시만 둔다.
- 바꾼 뒤에는 `python -m pytest`. 빠르게는 `python -m pytest tests/test_config.py tests/test_scoring.py`.

보안

- API key, token, 내부 서버 주소를 코드, yaml, 노트북, 문서, commit 에 적지 않는다. `secrets.env` 와 환경변수만 쓴다.
- key 값을 출력하거나 로그에 남기지 않는다 (`secrets.mask` 사용). 결과 폴더에는 key 이름만 기록된다.
- commit 전에 `python -m ts2img doctor`. `.gitignore` 를 느슨하게 고치지 않는다 (`tests/test_secrets.py` 가 검사한다).
- `.gitignore` 에 폴더 이름을 추가할 때는 `/` 로 시작해 위치를 고정한다. Windows 는 대소문자를 구분하지 않아서, `TSRBench/` 규칙이 `ts2img/benchmarks/tsrbench/` 코드까지 제외한 적이 있다 (지금은 `/TSRBench/`).
- 공식 TSRBench 저장소에는 주석 처리된 key 문자열이 남은 파일이 있다. 쓰지 말고, `third_party/` 를 git 에 올리지 않는다.

문서

- `README.md` 는 팀원이 따라 할 수 있는 최소한만. 길어지면 폴더별 README 로 옮긴다.
- 사실을 적을 때는 확인한 것과 추정한 것을 구분한다.

실험 해석

- chart 간 차이는 반복 간 흔들림(`perception_baseline` 의 "실행 간 변동")과 비교해서 말한다.
- 보고서의 "공식 방식" 수치만 인용하지 않는다. 답 없음, context 초과 건수를 같이 본다.
- 여러 chart 를 비교했으면 Holm 보정 p 를 쓴다.

## 7. 이 문서 고치기

- 사실이 바뀌거나 새로 확인되면 3번, 5번을 고친다. "확인하지 못한 것" 을 확인했으면 그 항목을 지우고 결과를 3번에 적는다.
- 결정을 바꾸면 4번의 해당 줄을 지우지 말고 새 줄을 추가한다 (날짜, 새 결정, 이유). 왜 바뀌었는지가 남아야 한다.
- 규칙이 실제 작업과 맞지 않으면 규칙을 고친다. 고친 이유를 아래 기록에 한 줄 남긴다.
- 대화에서 정해진 중요한 요구나 선호가 있으면 여기에 옮겨 적는다. 다음 작업자(사람이든 AI 든)는 그 대화를 볼 수 없다.

변경 기록

| 날짜 | 내용 |
| --- | --- |
| 2026-11-12 | 처음 작성. 실험 도구 전체 구현 직후의 상태 |
| 2026-11-13 | push 전 Colab 시험 방법 추가 (2번 표, 4번, 5번) |
| 2026-11-13 | Colab 에서 실제 모델(`qwen3-vl-4b`)로 smoke 실행. 확인된 내용을 3번으로 옮기고 5번을 줄임 |
| 2026-11-13 | 채점 오류 수정(adapter version 2), `max_tokens` 기본값을 공식과 같게 변경 |
| 2026-11-14 | pack_source, 유료 비용 기능 삭제. README, 노트북, yaml 주석 정리 |
| 2026-11-25 | applied_forecast 설정을 추가. 모델 실행 전 |
| 2026-11-25 | applied_forecast 입력 창을 168시간에서 672시간으로 변경 (version 2) |
| 2026-11-25 | applied_forecast_scale3 추가. vision 과 차트 3배만 |
| 2026-11-25 | applied_peak_hour 추가. 교통량 피크 시각, vision, ±1시간 |
| 2026-11-25 | applied_peak_hour_scale3 추가. 같은 문항, clock_days scale 3 |
| 2026-11-25 | 피크 시각 입력을 4주로 늘리고 주 시작 세로선을 굵게 함 (peak-hour-v2) |
| 2026-11-25 | 4주를 주별 3배 차트 4장으로 가로 배치 (peak-hour-v3). qwen3-vl-4b context 32768 |
| 2026-11-25 | 피크 문항을 95% 시간 집합의 F1로 바꿈 (peak-hours-v1). 차트는 v3 과 같음 |
| 2026-11-25 | 주별 차트 4장 사이에 간격을 두고 테두리를 넣음 (clock_days v4) |
| 2026-11-25 | 주별 차트에 00:00, 06h, 12h, 18h 눈금을 넣음 (clock_days v5) |
| 2026-11-25 | 주별 차트에 3시간마다 세로선을 넣음. 글자는 6시간 간격 (clock_days v6) |
| 2026-11-25 | 차트는 최근 3주만 보여주고 시각 숫자 라벨을 뺌 (clock_days v7). 실험은 아직 안 돌림 |
| 2026-11-25 | 주별 차트 x축을 데이터 시작·끝에 맞춤 (clock_days v8) |
| 2026-11-25 | 질문을 3주 차트(자정 짙은 선, 3시간 옅은 선)에 맞추고, 95% 시각을 모두 배열로 내라고 함 (peak-hours-v3) |
| 2026-11-25 | 차트는 최근 2주, 시간 세로선과 가로축 글자 없음 (clock_days v9, peak-hours-v4). 실험은 아직 안 돌림 |
| 2026-11-25 | 2주 차트의 오른쪽 패널에도 vehicles 축을 붙임 (clock_days v10) |
| 2026-11-25 | applied_seoul_peak_scale3 추가. 따릉이 ≥1000대 피크 시각, bike_peak scale3 |
| 2026-11-25 | applied_seoul_peak_gemini 추가. 동일 문항·차트, 모델만 gemini-hydrogen |
| 2026-11-25 | applied_seoul_peak_gemini_text 추가. 동일 문항·모델, text 표 입력 |
| 2026-11-25 | applied_seoul_peak_lab / applied_seoul_forecast_lab 추가. 노트북·README 다운로드 안내 |
