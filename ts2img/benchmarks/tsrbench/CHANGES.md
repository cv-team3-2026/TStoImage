# TSRBench 공식 코드와 다른 점

기준: 공식 코드 [tianyi-lab/TSRBench](https://github.com/tianyi-lab/TSRBench) commit `084e3f0` (`third_party/TSRBench`).
공식 코드를 직접 고치지는 않았습니다. `ts2img/` 에 다시 구현했고, 그 과정에서 **공식 코드와 다르게 동작하는 부분**을 여기에 적습니다.

- 다른 동작을 추가하거나 바꾸면 이 파일에 항목을 추가합니다. 이유와 되돌리는 방법(있다면)을 같이 적습니다.
- "기본값이 다름" 은 결과 숫자에 영향을 줄 수 있는 항목입니다. 논문 수치와 비교할 때 이 목록을 확인하세요.

## 재현한 공식 스크립트

| 입력 조건 | 일반 task | abductive |
| --- | --- | --- |
| vision | `vision_opensource/vision_inference_opensource.py` | `vision_opensource/vision_inference_opensource_abductive.py` |
| text | `text_opensource/text_inference_opensource.py` | `text_opensource/text_inference_opensource_abductive.py` |
| text+vision | `multimodal_gpt/evaluate_gpt_multimodal.py` | `multimodal_gpt/evaluate_gpt_abductive_multimodal.py` |
| chart | 위 vision 스크립트의 `generate_image_from_timeseries`, `generate_basketball_visualization` | |
| 채점 | `evaluation/evaluate.py` 의 `evaluate_MCQ` | |

text+vision 은 공식 코드에 오픈소스 모델용 스크립트가 없어 GPT 용을 따랐습니다.
prompt 문구, chart 모양(크기, 색, 선 굵기, JPEG 100dpi), message 순서(text 다음 이미지), JSON schema 는 공식 코드와 같습니다.
chart 는 `augmentation_examples/*/baseline.png` 과 크기, 내용이 같은지 테스트로 확인합니다 (`tests/test_tsrbench_data.py`).

## 1. 데이터

| 항목 | 공식 | 여기 | 이유 |
| --- | --- | --- | --- |
| 데이터 저장소 | `download_data.py` 가 `ParadiseYu/TSRBench` 를 받음 | `umd-zhou-lab/TSRBench`, revision `de20bef3` 고정 | 공식이 가리키는 저장소에 접근할 수 없음. 논문에 적힌 공개 데이터를 사용 |
| 파일 경로와 이름 | 스크립트마다 다름 (`event_forecast`, `pattern_decision`, `math_reasoning` 등) | 공개 데이터의 실제 이름 (`event_prediction`, `qualitative_decision`, `numerical_reasoning`) | 공식 스크립트의 이름이 공개 데이터와 맞지 않음 |
| task 구분 | 파일 이름에 `temporal` / `etiological` 이 들어 있는지로 판단 | 같은 규칙을 unit 이름에 적용 | 동작은 같음 |

공개 데이터의 perception 하위 분류 값은 `Anolmaly Detection` (오타) 입니다. 데이터는 그대로 두고 task 이름만 `perception/anomaly_detection` 으로 부릅니다.

## 2. prompt

공개 데이터가 공식 스크립트의 가정과 맞지 않아 그대로는 실행되지 않는 경우에만 맞췄습니다.

| 항목 | 공식 코드의 동작 | 여기 | 영향 범위 |
| --- | --- | --- | --- |
| perception, text 조건 | `sample["choices"]`, `sample["name_of_series"]` 가 없어 오류로 문항을 건너뜀 | 질문 본문에 이미 있는 `<ts><ts/>` 자리에 값을 넣음. " Here are the time series ..." 문장은 붙이지 않음 | perception 700 |
| 이름 없는 문항, text 조건 | `name_of_series` 가 없으면 오류 | 이름을 `Series 1`, `Series 2` ... 로 채움 | numerical 50 |
| 이름 수가 series 수보다 적은 문항, text 조건 | placeholder 가 모자라 오류 | 모자란 이름을 `Series N` 으로 채움 | time_series_forecasting 720 (이름 1개, series 4개) |
| perception, vision / text+vision | 질문 속 `<ts><ts/>` 를 그대로 보냄. 선택지는 본문에 있고 "Select from the options below:" 뒤는 빔. 본문의 "You must start response from A)..." 와 JSON 지시가 같이 들어감 | **같음 (그대로 둠)**. `ts_placeholder` 옵션으로 `<ts><ts/>` 를 다른 문자열로 바꿀 수 있음 | perception 700 |
| chart 의 series 이름 | 이름이 없으면 `series_0`, `series_1` | **같음**. chart 옵션 `names` 로 바꿀 수 있음 | perception 700 |

마지막 두 항목은 고치지 않았지만 알아 둘 점입니다. perception 질문은 "time series 1" 이라고 부르는데 chart 에는 `series_0` 이라고 적힙니다.

## 3. 요청

| 항목 | 공식 | 여기 (기본값) | 되돌리기 / 비고 |
| --- | --- | --- | --- |
| sampling | 보내지 않음 (서버 기본값) | **같음** (`sampling: official`) | `deterministic` 또는 직접 지정 가능 |
| `max_tokens` | 보내지 않음 (상한 없음) | **같음** (`max_tokens: null`) | 서버가 context 가 허용하는 만큼 생성한다. 그래서 실제 상한은 `models.yaml` 의 `max_model_len` 이 정한다 (공식 서빙은 제한하지 않음). 느리면 실험 yaml 에 숫자를 적어 줄일 수 있다. 길이 한도에서 잘린 응답 수는 보고서에 표시 |
| `reasoning_effort` | text, text+vision, GPT 용 스크립트는 보냄 (`low` 등) | 보내지 않음 | reasoning 모델이면 `models.yaml` 의 `request: {reasoning_effort: low}`. Qwen3-VL-Instruct 에는 해당 없음 |
| 답 재요청 | vision: 답이 글자로 안 읽히면 최대 10회. text: 없음. abductive vision: JSON 으로 안 읽히면 최대 10회 | 모든 조건에서 답 글자를 못 찾으면 최대 10회 (`answer_retries`) | temperature 0 이면 재요청하지 않음 (같은 답이 나오므로). `answer_retries: 0` 으로 끌 수 있음 |
| 요청 실패 재시도 | 스크립트마다 다름 | 일시적 오류(429, 5xx, timeout)만 6회까지 재시도. 그래도 실패하면 `error` 로 기록하고 다음 실행에서 다시 시도 | 공식은 실패한 문항을 결과에서 뺌 |
| context 초과 | 오류로 문항을 건너뜀 (결과에서 빠짐) | `context_overflow` 로 기록하고 **오답으로 집계**. 건수를 보고서에 표시 | 빠진 문항이 정확도를 올리지 않게 하기 위함 |
| 동시 요청 | process 32개 (text 는 4개) | thread 8개 (`concurrency`) | 결과에 영향 없음 |
| text 값 간격 | 오픈소스용: 전부. GPT 용: float 4개 중 1개, 그 외 6개 중 1개 | 전부 (`text_stride: 1`) | `text_stride: gpt_official` |

## 4. 서빙 (vLLM)

공식 스크립트는 `--tensor-parallel-size 4 --trust-remote-code --limit-mm-per-prompt.video 0` 만 주고 나머지는 vLLM 기본값입니다 (모델: Qwen3-VL-8B / 32B, GPU 4장).
여기서는 `configs/models.yaml` 에 모델마다 적습니다. 공식과 다른 점:

- 모델 revision 을 고정한다.
- T4 에서는 `dtype: float16` 으로 적어 두었다 (T4 는 bfloat16 연산을 기본 지원하지 않는다). 공식은 지정하지 않음(vLLM 기본값).
- `max_model_len` 을 제한한다 (GPU memory 때문). 넘는 문항은 위의 context 초과 규칙을 따른다.
- 논문은 4B 모델을 쓰지 않았다. `qwen3-vl-4b` 결과는 논문 수치와 직접 비교할 수 없다.

## 5. 채점

| 항목 | 공식 | 여기 |
| --- | --- | --- |
| 응답 읽기 | `eval(응답)` | `json.loads` -> `ast.literal_eval` -> 가장 바깥 `{...}` 순서로 시도. 코드를 실행하지 않음 |
| 읽지 못한 응답 | 분모에서 뺌 | 두 값을 같이 보고: **정확도**(오답 처리), **공식 방식**(분모에서 뺌) |
| 답 글자 추출 | `answer` 값에서 `, $ 공백 * ( )` 를 지운 첫 글자 | 같음. dict 로 안 읽히면 추가로 찾음 (`parse: fallback`, "공식 방식" 분모에는 넣지 않음). `{` 로 시작하는 응답(잘린 JSON 등)은 `"answer": "B"` 항목이 있을 때만 인정하고, 글로 답한 응답은 `B)`, `answer is B` 형태를 찾음 |

길이 한도에서 잘린 응답은 `answer` 항목이 없으므로 "답 없음"이 되고, 재요청 대상이 됩니다 (공식 vision 스크립트도 이런 응답은 다시 요청합니다).
version 1 에서는 잘린 풀이 본문의 "option C is incorrect" 같은 표현에서 글자를 집어 답으로 처리하는 오류가 있었습니다.

`eval` 을 쓰지 않는 이유: 모델 출력을 그대로 실행하게 되고, 형식이 조금만 어긋나도 문항이 통계에서 빠져 정확도가 높게 나올 수 있습니다.

## 6. 공식 코드에 없는 것

chart 변형(`ts2img/charts/`), 반복 실행과 통계(신뢰구간, McNemar, Holm), 재개, 비용 추정은 이 프로젝트에서 추가한 것입니다.

## 변경 기록

| 날짜 | 내용 |
| --- | --- |
| 2026-11-12 | 처음 작성 (adapter version 1) |
| 2026-11-13 | adapter version 2: 잘린 JSON 응답에서 풀이 본문의 글자를 답으로 집던 오류 수정. `max_tokens` 기본값을 2048 에서 공식과 같은 "보내지 않음" 으로 변경 |
