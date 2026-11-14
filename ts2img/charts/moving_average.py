"""공식 chart 위에 이동평균 추세선을 겹쳐 그린다.

yaml 예: {use: moving_average, window: 8}
"""
from ts2img.charts._render import Style, draw, rolling_mean
from ts2img.charts.base import fig_to_image

VERSION = 1


def render(
    sample,
    window: int = 8,
    ma_color: str = "darkorange",
    ma_linewidth: float = 2,
    raw_alpha: float = 0.45,          # 원본 선의 투명도. 1 이면 그대로
    legend: bool = True,
    linewidth: float | None = None,
    names: str | None = None,
    dpi: int = 100,
    fmt: str = "jpeg",
):
    label = f"Moving average (window={window})"

    def extra(ax, i, values, color):
        for line in ax.get_lines():
            if line.get_gid() != "ma" and line.get_label() != "Critical Moment":
                line.set_alpha(raw_alpha)
        ax.plot(
            rolling_mean(values, window), color=ma_color, linewidth=ma_linewidth,
            label=label if i == 0 else None, gid="ma",
        )
        if legend and i == 0 and sample.kind != "abductive":
            ax.legend(loc="best", fontsize=7)

    return [fig_to_image(draw(sample, Style(linewidth=linewidth, names=names), extra), dpi=dpi, fmt=fmt)]
