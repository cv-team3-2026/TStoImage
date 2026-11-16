# benchmarks

벤치마크마다 폴더 하나입니다. 벤치마크에 따라 달라지는 것(데이터 받기, task 구조, 전처리, prompt, 채점)을 이 안에 모아 둡니다.
chart, 실행기, 보고서는 벤치마크를 모르고 `Sample` 형식만 봅니다.

```
benchmarks/
  base.py            공통 형식: Sample, Series, PromptSpec, Score, Benchmark
  __init__.py        registry (_REGISTRY 에 등록)
  tsrbench/
    adapter.py       다운로드, task 계층, 로더
    prompts.py       공식 prompt 재현 (text / vision / text+vision)
    scoring.py       객관식 채점
    CHANGES.md       공식 코드와 다르게 동작하는 부분의 기록
```

## TSRBench task 이름

파일(unit) 12개, task 15개입니다. perception 은 4개 task 가 한 파일에 있습니다.

```
tsrbench                                   전부 (4,125문항)
tsrbench/perception                        700
tsrbench/perception/pattern_recognition    371
tsrbench/perception/anomaly_detection      129
tsrbench/perception/similarity_analysis    113
tsrbench/perception/noise_understanding     87
tsrbench/reasoning                         7개 task 전부
tsrbench/reasoning/{abductive, causal, deductive, etiological, inductive, numerical, temporal_relation}
tsrbench/prediction/{time_series_forecasting, event_prediction}
tsrbench/decision/{qualitative_decision, quantitative_decision}
```

데이터는 처음 실행할 때 `data/tsrbench/<revision>/` 에 자동으로 받습니다. 이미 있으면 건너뜁니다.
HuggingFace revision 을 고정해 두었으므로 데이터가 조용히 바뀌는 일은 없습니다.

## 새 벤치마크 추가

1. `benchmarks/<이름>/adapter.py` 에 `Benchmark` 를 상속한 class 를 만든다.

   | method | 역할 |
   | --- | --- |
   | `units()` | run 폴더 단위 목록 (보통 데이터 파일 하나) |
   | `leaf_tasks()` | 보고서 집계 단위 목록 |
   | `select(path)` | `"a/b"` 같은 경로를 `Selection(unit, subtasks)` 목록으로 |
   | `ensure_data(units)` / `has_data(unit)` / `root()` | 다운로드 (있으면 건너뜀) |
   | `load(unit)` | `Sample` 목록. 전처리는 여기서 |
   | `prompt(sample, modality, opts)` | `PromptSpec(text, ...)` |
   | `score(sample, response)` | `Score(pred, correct, parse)` |
   | `options(sample)` | 가능한 정답 글자 목록 |

2. `benchmarks/__init__.py` 의 `_REGISTRY` 에 `"<이름>": "ts2img.benchmarks.<이름>.adapter:<Class>"` 를 추가한다.
3. 실험 yaml 의 `benchmarks:` 에 `<이름>/...` 으로 쓴다.

지킬 것

- `Sample.id` 는 `"<unit>#<번호>"` 형식으로, 같은 문항이면 항상 같아야 한다 (재개와 문항 단위 비교의 기준).
- prompt 나 로더의 동작을 바꾸면 class 의 `version` 을 올린다. 올리지 않으면 예전 결과와 섞인다.
- 원본 벤치마크의 코드와 다르게 동작하는 부분은 그 폴더의 `CHANGES.md` 에 적는다.
- 객관식이 아닌 벤치마크(수치 예측 등)는 `Score` 와 보고서 통계를 넓혀야 한다. 지금 보고서는 정오(맞음/틀림) 기준이다.
