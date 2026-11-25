# applied

실제 시계열에서 **숫자 나열(text)** 과 **line chart(vision)** 를 비교한다.
데이터셋마다 벤치마크가 다르다. 보고서의 정확도는 합쳐지지 않는다.

| 벤치마크 | 데이터 | 받는 방법 |
| --- | --- | --- |
| `applied_metro` | Metro Interstate 시간별 통행량 | 실행 시 UCI 자동 |
| `applied_seoul` | Seoul Bike 시간별 도시 전체 대여량 | 실행 시 UCI 자동 |
| `applied_kpx` | KPX 시간별 전력수요 | CSV 를 직접 둔다 |
| `applied_seoul_peak` | 위 Seoul Bike + 기온·강수 | 실행 시 UCI 자동 (같은 zip) |
| `applied_metro_peak` | Metro 피크 시각 | 실행 시 UCI 자동 |

## 데이터 받기

Seoul 실험만 다른 컴퓨터에서 돌릴 때:

```bash
python -m ts2img download applied_seoul applied_seoul_peak
```

- 저장 위치: `data/applied/seoul_bike/SeoulBikeData.csv`
- 출처: [UCI Seoul Bike Sharing Demand](https://archive.ics.uci.edu/dataset/560/seoul+bike+sharing+demand)
- 네트워크가 되면 `run` / `ensure_data` 가 없어도 zip 을 받아 푼다. 위 명령은 미리 받아 두는 용도다.
- `data/` 는 git 에 올리지 않는다.

Metro 도 필요하면:

```bash
python -m ts2img download applied_metro applied_seoul applied_seoul_peak
```

KPX 는 자동 다운로드가 없다. `data/applied/kpx/hourly.csv` 를 직접 둔다.
받는 곳: [공공데이터포털 시간별 전국 전력수요량](https://www.data.go.kr/data/15065266/fileData.do).

## 대형 VLM 비교용 실험 (lab)

다른 PC 의 OpenAI-compatible 서버(예: Qwen-VL 230B급)에 붙일 때:

| 실험 yaml | 과제 | 차트 | modality |
| --- | --- | --- | --- |
| `applied_seoul_peak_lab` | 내일 ≥1000대/시 피크 시각 집합 (F1), 60문항 | `bike_peak` scale 3 | text, vision, text+vision |
| `applied_seoul_forecast_lab` | 다음 24h 평균 5단계 (A–E), 90문항 | `line_style` scale 3 | text, vision, text+vision |

1. `configs/models.yaml` 의 `lab-vlm.model` 을 서버 모델 이름으로 바꾼다.
2. `secrets.env` 에 `LAB_VLM_BASE_URL=http://<호스트>:8000/v1` (필요하면 `LAB_VLM_API_KEY`).
3. 데이터를 받은 뒤 실행한다.

```bash
python -m ts2img download applied_seoul applied_seoul_peak
python -m ts2img run applied_seoul_peak_lab --background
python -m ts2img run applied_seoul_forecast_lab --background
python -m ts2img report applied_seoul_peak_lab
python -m ts2img report applied_seoul_forecast_lab
```

짧게 확인: `--limit 5`. 로컬 4B 로 시험만 할 때는 `--models qwen3-vl-4b --auto-serve`.

## 문항 요약

- `applied_seoul` / metro / kpx: 직전 4주(672시간) → 다음 24시간 평균이 직전 24시간보다 훨씬 낮음/낮음/비슷/높음/훨씬 높음.
- `applied_seoul_peak`: 직전 7일 대여량 + 내일 기온·강수 예보 → 내일 0–23시 중 1000대/시 이상인 시각 전부. 채점 F1.
- 따릉이 값은 도시 전체 대여량이다. 거치대 하나 품절은 이 문항으로 말하지 않는다.

## 기타 실험

```bash
python -m ts2img run applied_forecast --benchmarks applied_metro,applied_seoul --auto-serve
python -m ts2img run applied_forecast_scale3 --auto-serve
python -m ts2img run applied_seoul_peak_scale3 --auto-serve
```
