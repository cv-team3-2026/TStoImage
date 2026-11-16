# 실험 보고서: perception_baseline

perception 기준 성능과 반복 실행 간 흔들림

- 생성: 2026-11-15T12:25:36+00:00
- 진행: 6300 / 6300 요청 완료 (100.0%)
- 대상: tsrbench/perception | 모델: qwen3-vl-4b | 입력: text, vision, text+vision
- sampling: `official`, repeats 3, max_tokens 없음(공식), text 값 간격 1
- 비교 기준(baseline): `tsrbench_baseline`

읽는 법

- 정확도: 처리가 끝난 문항 중 정답 비율. 답 글자를 못 뽑은 응답과 context 초과 문항은 오답으로 친다. 대괄호는 95% 신뢰구간.
- 공식 방식: TSRBench 공식 채점처럼 JSON 으로 읽히지 않은 응답을 분모에서 뺀 값.
- 차이: 같은 문항끼리 baseline 과 비교한 값(%p). 얻음/잃음 = baseline 에서 틀렸다가 맞은 / 맞았다가 틀린 문항 수.
- p: McNemar exact test. p(Holm) 은 같은 표 안의 여러 비교를 보정한 값이다.

## tsrbench / qwen3-vl-4b / vision

| chart | 문항 수 | 정확도 % [95% CI] | 차이 %p [95% CI] | 얻음 / 잃음 | p | p (Holm) | 공식 방식 % | 답 없음 | 처리율 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **tsrbench_baseline** (baseline) | 700 | 58.4 [54.7, 62.0] |  |  |  |  | 58.7 | 3 | 100% |

기준선: 최빈 정답(A)만 찍으면 42.6% / text 만 입력(chart 없음) 51.0% [47.3, 54.7], 700문항

![accuracy](figures/accuracy_qwen3-vl-4b_vision.png)

### task 별 정확도 % (괄호: baseline 대비 %p)

| task | 문항 | tsrbench_baseline |
| --- | --- | --- |
| perception/anomaly_detection | 129 | 49.6 |
| perception/noise_understanding | 87 | 52.9 |
| perception/pattern_recognition | 371 | 61.2 |
| perception/similarity_analysis | 113 | 63.7 |

### 실행 간 변동 (같은 설정 반복)

| chart | 반복별 정확도 % | 평균 % | 범위 %p | r0-r1 사이 정오가 바뀐 문항 % |
| --- | --- | --- | --- | --- |
| tsrbench_baseline | 58.4, 59.7, 58.3 | 58.8 | 1.4 | 13.9 |

chart 간 차이가 이 범위보다 작으면 실행 간 변동과 구분되지 않는다. 위 표의 차이와 p 는 첫 번째 실행(r0) 기준이다.

### 비용과 입력 크기

| chart | 입력 tok | 출력 tok | 응답 시간 s (중앙값) | 이미지 수 | 이미지 px (최빈) | 이미지 KB | 재요청 | 길이 한도로 잘림 | 오류 | context 초과 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tsrbench_baseline | 244 | 325 | 1.3 | 1.0 | 438x236 | 17 | 23 | 3 | 0 | 0 |

## tsrbench / qwen3-vl-4b / text+vision

| chart | 문항 수 | 정확도 % [95% CI] | 차이 %p [95% CI] | 얻음 / 잃음 | p | p (Holm) | 공식 방식 % | 답 없음 | 처리율 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **tsrbench_baseline** (baseline) | 700 | 51.6 [47.9, 55.3] |  |  |  |  | 51.6 | 0 | 100% |

기준선: 최빈 정답(A)만 찍으면 42.6% / text 만 입력(chart 없음) 51.0% [47.3, 54.7], 700문항

![accuracy](figures/accuracy_qwen3-vl-4b_text_vision.png)

### task 별 정확도 % (괄호: baseline 대비 %p)

| task | 문항 | tsrbench_baseline |
| --- | --- | --- |
| perception/anomaly_detection | 129 | 43.4 |
| perception/noise_understanding | 87 | 49.4 |
| perception/pattern_recognition | 371 | 54.4 |
| perception/similarity_analysis | 113 | 53.1 |

### 실행 간 변동 (같은 설정 반복)

| chart | 반복별 정확도 % | 평균 % | 범위 %p | r0-r1 사이 정오가 바뀐 문항 % |
| --- | --- | --- | --- | --- |
| tsrbench_baseline | 51.6, 51.3, 52.1 | 51.7 | 0.9 | 6.3 |

chart 간 차이가 이 범위보다 작으면 실행 간 변동과 구분되지 않는다. 위 표의 차이와 p 는 첫 번째 실행(r0) 기준이다.

### 비용과 입력 크기

| chart | 입력 tok | 출력 tok | 응답 시간 s (중앙값) | 이미지 수 | 이미지 px (최빈) | 이미지 KB | 재요청 | 길이 한도로 잘림 | 오류 | context 초과 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tsrbench_baseline | 1288 | 14 | 0.5 | 1.0 | 438x236 | 17 | 0 | 0 | 0 | 0 |

## tsrbench / qwen3-vl-4b / text (chart 없음)

| 문항 수 | 정확도 % [95% CI] | 공식 방식 % | 답 없음 | context 초과 | 처리율 |
| --- | --- | --- | --- | --- | --- |
| 700 | 51.0 [47.3, 54.7] | 51.1 | 1 | 0 | 100% |

| task | 문항 | 처리됨 | 정확도 % | context 초과 |
| --- | --- | --- | --- | --- |
| perception/anomaly_detection | 129 | 129 | 41.9 | 0 |
| perception/noise_understanding | 87 | 87 | 41.4 | 0 |
| perception/pattern_recognition | 371 | 371 | 53.1 | 0 |
| perception/similarity_analysis | 113 | 113 | 61.9 | 0 |

## chart 예시

같은 문항을 chart 별로 그린 것 (행 = chart, 열 = 문항).

### perception

![gallery](figures/gallery_perception.jpg)

## 실행 환경과 설정

| model | 이름 | 서빙 설정 | 보낸 sampling | 서버 기본 sampling |
| --- | --- | --- | --- | --- |
| qwen3-vl-4b | Qwen/Qwen3-VL-4B-Instruct | dtype=float16, limit_mm_per_prompt={'image': 4}, revision=ebb281ec70b05090aa6165b016eac8ec08e71b17 | 없음 (서버 기본값 사용) | {'do_sample': True, 'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'repetition_penalty': 1.0} |

- OS Linux 6.8.0-147-generic, Python 3.12.16, CPU Intel(R) Core(TM) Ultra 7 270K Plus (24 threads), RAM 62.1 GB
- GPU: NVIDIA GeForce RTX 5090 32GB | Colab: 아니오
- 패키지: matplotlib 3.11.2, pillow 13.0.0, numpy 2.5.4, openai 3.49.0, huggingface_hub 2.4.0, PyYAML 6.0.3, rich 15.0.0
- git commit: a6b8b573

run 폴더 (raw 결과)

- `runs/tsrbench/perception/qwen3-vl-4b/text/none__6a590113` : tsrbench/perception | qwen3-vl-4b | text | none
- `runs/tsrbench/perception/qwen3-vl-4b/text/none__7577bde5__r1` : tsrbench/perception | qwen3-vl-4b | text | none r1
- `runs/tsrbench/perception/qwen3-vl-4b/text/none__de4858ff__r2` : tsrbench/perception | qwen3-vl-4b | text | none r2
- `runs/tsrbench/perception/qwen3-vl-4b/vision/tsrbench_baseline__5357ce0e` : tsrbench/perception | qwen3-vl-4b | vision | tsrbench_baseline
- `runs/tsrbench/perception/qwen3-vl-4b/vision/tsrbench_baseline__5b1ecf59__r1` : tsrbench/perception | qwen3-vl-4b | vision | tsrbench_baseline r1
- `runs/tsrbench/perception/qwen3-vl-4b/vision/tsrbench_baseline__f0999d79__r2` : tsrbench/perception | qwen3-vl-4b | vision | tsrbench_baseline r2
- `runs/tsrbench/perception/qwen3-vl-4b/text+vision/tsrbench_baseline__210a1cd1` : tsrbench/perception | qwen3-vl-4b | text+vision | tsrbench_baseline
- `runs/tsrbench/perception/qwen3-vl-4b/text+vision/tsrbench_baseline__dcee9e47__r1` : tsrbench/perception | qwen3-vl-4b | text+vision | tsrbench_baseline r1
- `runs/tsrbench/perception/qwen3-vl-4b/text+vision/tsrbench_baseline__07f0572c__r2` : tsrbench/perception | qwen3-vl-4b | text+vision | tsrbench_baseline r2

