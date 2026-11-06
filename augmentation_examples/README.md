# augmentation_examples

image augmentation 팀용 예시 시계열 9개입니다. TSRBench(ICML 2026)에서 모양과 구조가 서로 다른 것으로 골랐습니다.

## 사용법

- 시계열 값은 각 폴더의 `data.json`에 있습니다. `name_of_series`가 시계열 이름, `timeseries`가 값 리스트(시계열이 여러 개면 리스트의 리스트)입니다. 일부는 `timestamps`나 이벤트 텍스트가 추가로 들어 있습니다.
- 이 `data.json`을 읽어서 라인차트로 그리고, 그 위에 augmentation을 적용한 결과 이미지를 가져오면 됩니다.
- `baseline.png`는 TSRBench 논문의 기본 렌더링을 재현한 "증강 전" 그림입니다. 비교 기준으로 쓰세요.
- `question.txt`에는 그 시계열로 모델이 풀 질문, 선택지, 정답과 이 예시를 고른 이유가 적혀 있습니다. -> 이건 그냥 참고용입니다!

여기서 augmentation은 학습용 무작위 변형(회전·반전·크롭)이 아니라, 시계열의 특징이 그림에 더 잘 드러나게 하는 렌더링 설계를 뜻합니다. 예: 날짜 축과 사건 마커, 이동평균·추세선, 이상 구간 음영, 값 라벨, 다변량 정규화 후 겹치기, 해상도·크기 변화.

## 기준 렌더링 (TSRBench 공식 설정)

단일 시계열은 5×2인치 파란 꺾은선, 여러 개면 세로 subplot 6×(개수×1.3)인치. 격자선, 100 dpi, x축은 인덱스. 논문에서 100 dpi가 최적이었고 200·400 dpi는 오히려 성능이 떨어졌습니다.

## 예시 목록

| 폴더 | 시계열 | 보고 싶은 것 |
| --- | --- | --- |
| 01_perception_pattern_seasonality | 1개, 128점 | 추세·계절성·노이즈 혼합. 지배적 패턴 |
| 02_perception_anomaly_local | 1개, 128점 | 국소 이상치 강조 |
| 03_perception_noise_type | 1개, 128점 | 가산/승산 노이즈 구분 |
| 04_perception_two_series_amplitude | 2개, 128점 | 두 시계열 비교 (겹칠지, 따로 그릴지) |
| 05_temporal_relation_goldstein | 1개, 77점 + 날짜 | 사건 시점 마커, 날짜 축 |
| 06_abductive_basketball | 4개, 299점 | 스케일이 다른 시계열 동시 표현, 과거/미래 경계 |
| 07_event_prediction_weather_5var | 5개, 24점 | 단위가 제각각인 다변량, 축 눈금 |
| 08_quant_decision_price_series | 1개, 207점 | 이동평균·볼린저밴드 오버레이 |
| 09_tsf_news_plus_stock | 4개, 35점 | 뉴스 + 주가 (발표 running example과 같은 구조) |

01~04는 합성 데이터라 정답 패턴이 명확하고, 05~09는 실데이터입니다.

## 출처

- 데이터: https://huggingface.co/datasets/umd-zhou-lab/TSRBench
- 논문: https://arxiv.org/abs/2601.18744
- 렌더링 코드 원본: https://github.com/tianyi-lab/TSRBench (`inference/vision_gpt/vision_inference.py`)
