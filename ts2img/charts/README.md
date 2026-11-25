# charts

이 폴더의 `.py` 파일 하나가 chart 하나입니다. 파일을 추가하면 바로 yaml 에서 쓸 수 있습니다 (등록 절차 없음).
`_` 로 시작하는 파일과 `base.py`, `post.py` 는 chart 가 아니라 공용 코드입니다.

## 지금 있는 chart

| 이름 | 하는 일 | 주요 옵션 |
| --- | --- | --- |
| `tsrbench_baseline` | TSRBench 공식 chart. 비교 기준이라 옵션이 없다 | - |
| `line_style` | 공식 chart 에서 모양만 바꾼다 | `linewidth`, `color`, `scale`(크기 배율), `dpi`, `grid`, `marker`, `names`, `fmt`, `tick_labelsize`, `y_ticks` |
| `moving_average` | 이동평균 추세선을 겹쳐 그린다 | `window`, `raw_alpha`, `legend` |
| `overlay_legend` | 여러 series 를 한 축에 겹치고 legend 로 구분한다 | `normalize`(none/zscore/minmax), `legend_loc` |
| `multi_view` | 변환한 그림을 여러 장 보낸다 | `views`(full/smooth/diff), `window` |
| `tile_overlap` | 전체 그림 아래에 앞·뒤 구간을 겹쳐 붙인다 | `head`, `tail` |
| `panel_row` | 여러 패널을 좌우로 배치한다. 하나면 공식 chart | `names` |
| `zoom_crop` | 급변 구간만 크게 보여 준다. 축은 없다 | `half`, `scale` |
| `zoom_window` | 급변 구간을 눈금이 있게 다시 그린다 | `half` |
| `wide_x` | 높이는 유지하고 가로만 늘린다 | `width` |
| `recolor_line` | 데이터 선 색만 바꾼다 | `color` |
| `shade_jumps` | 급변 구간에 옅은 음영을 넣는다 | `z`, `color`, `alpha` |
| `mark_jumps` | 급변 지점에 인덱스를 표시한다 | `z`, `max_marks` |
| `shared_y` | 여러 패널의 y축 범위를 같게 맞춘다. 하나면 공식 chart | - |
| `linear_trend` | 원래 선 위에 직선 추세선을 얇게 겹친다 | - |
| `aspect` | 평균 기울기가 약 45도가 되게 패널 높이를 맞춘다 | - |
| `heatmap` | series 값을 시간 × 채널 색 지도로 그린다 | `dpi`, `fmt` |
| `gaf` | Gramian Angular Summation Field. series 마다 한 패널 | `max_points`, `dpi`, `fmt` |
| `spectrogram` | 구간별 주파수 세기를 로그 스케일로 그린다 | `nperseg`, `dpi`, `fmt` |
| `inner_filter` | 격자 없는 선 그래프의 안쪽에만 필터를 적용한다. 축과 글자는 그대로 | `op`(none/sharpen/blur/edge/erode), `strength`, `dpi`, `fmt` |
| `combo` | 가로 배치, 공유 y축, 배율, 급변 음영을 한 그림에서 고른다. 하나면 공식 chart | `layout`(row/stack), `share_y`, `scale`, `shade` |
| `none` | 이미지를 보내지 않는다 | - |

후처리(`post`)는 어느 chart 에나 붙일 수 있습니다: `{use: tsrbench_baseline, post: [sharpen]}`.
픽셀만 바꾸는 후처리: `sharpen`, `crop_margin`, `axis_sharpen`, `dark_mode`, `fade_grid`, `thicken_line`.
옵션의 기본값은 `python -m ts2img list` 로 볼 수 있습니다.

`names` 옵션: 공식 chart 는 이름 없는 series 를 `series_0`, `series_1` 로 적는데 perception 질문은 "time series 1", "time series 2" 라고 부릅니다.
`names: "Time Series {n}"` 으로 맞출 수 있습니다 (`{n}` 은 1부터, `{i}` 는 0부터).

## 새 chart 만들기

`ts2img/charts/my_chart.py`:

```python
"""한 줄 설명. (list 명령에 표시된다)

yaml 예: {use: my_chart, threshold: 2.5}
"""
from ts2img.charts._render import Style, draw
from ts2img.charts.base import fig_to_image

VERSION = 1   # 같은 옵션으로 그림이 달라지게 코드를 고치면 1 올린다


def render(sample, threshold: float = 3.0, dpi: int = 100, fmt: str = "jpeg"):
    def extra(ax, i, values, color):
        # 공식 chart 의 각 축에 덧그린다. i = series 번호, values = numpy array
        ax.axhline(values.mean() + threshold * values.std(), color="red", linewidth=1)

    fig = draw(sample, Style(), extra)          # 공식 chart 와 같은 배치로 그린 figure
    return [fig_to_image(fig, dpi=dpi, fmt=fmt)]
```

규칙

- 함수 이름은 `render`, 첫 인자는 `sample`. 나머지 keyword 인자가 yaml 옵션이 됩니다. 모르는 옵션을 yaml 에 쓰면 실행 전에 오류가 납니다.
- 돌려주는 값: 이미지 목록. `None` 이면 이미지 없이 보내고, 2장 이상이면 여러 장을 보냅니다.
- 이미지에 `caption` 을 주면(`fig_to_image(..., caption="...")`) 이미지 앞에 그 문장이 text 로 같이 들어갑니다.
  문장이 늘어나는 것 자체가 결과에 영향을 줄 수 있으니, 실험 yaml 에서 `method: {use: single_turn, image_captions: false}` 로 끈 조건과 같이 보는 것을 권합니다.
- `sample.series` 는 `Series(name, values)` 목록입니다. 완전히 새로 그리고 싶으면 `draw` 를 쓰지 않고 matplotlib 으로 직접 그려도 됩니다.
- **`VERSION` 을 꼭 관리하세요.** 그림이 달라졌는데 `VERSION` 이 같으면 예전 결과와 새 결과가 같은 폴더에 섞입니다.
- 같은 입력에는 항상 같은 그림이 나와야 합니다. 무작위 요소를 쓰면 seed 를 고정하세요.

확인

```bash
python -m ts2img preview charts --charts tsrbench_baseline "{use: my_chart, threshold: 2.5}" --task tsrbench/perception/anomaly_detection --n 4
python -m ts2img preview charts --charts my_chart --examples      # augmentation_examples 의 9개
```

그 뒤 실험 yaml 의 `charts:` 에 `- {use: my_chart, threshold: 2.5}` 를 추가합니다.
