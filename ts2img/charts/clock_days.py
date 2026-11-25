"""시간별 통행량을 주 단위 차트로 가로로 배치한다.

최근 2주만 그린다. 시간 세로선과 가로축 눈금 글자는 없다.
yaml 예: clock_days
         {use: clock_days, scale: 3}
"""
import io
from datetime import datetime

import matplotlib.pyplot as plt

from ts2img.charts.base import ChartImage

VERSION = 10
WEEK = 7 * 24
WEEKS_SHOWN = 2
# 패널 사이 간격(인치). 플롯 폭은 그대로 두고 그림만 넓힌다.
_GAP = 0.7


def render(sample, scale: float = 1.0, dpi: int = 100, fmt: str = "jpeg"):
    values = list(sample.series[0].values)
    xs = list(sample.x or range(len(values)))
    keep = WEEKS_SHOWN * WEEK
    if len(values) > keep:
        values = values[-keep:]
        xs = xs[-keep:]
    spans = [(i, min(i + WEEK, len(values))) for i in range(0, len(values), WEEK)] or [(0, len(values))]
    n = len(spans)
    gap = _GAP * scale
    fig, axes = plt.subplots(
        1,
        n,
        figsize=(12 * scale * n + gap * max(n - 1, 0), 3.6 * scale),
        sharey=True,
        squeeze=False,
    )
    fig.subplots_adjust(
        wspace=gap / (12 * scale),
        left=0.03,
        right=0.995,
        top=0.84,
        bottom=0.08,
    )
    axes = list(axes[0])
    for i, (a, b) in enumerate(spans):
        ax = axes[i]
        ax.set_facecolor("white")
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#222222")
            spine.set_linewidth(1.6 * scale)
        ax.plot(xs[a:b], values[a:b], color="#1f4e9c", linewidth=1.1 * scale)
        chunk = xs[a:b]
        if chunk and isinstance(chunk[0], datetime):
            ax.set_title(f"Week {i + 1}   {chunk[0]:%m-%d} – {chunk[-1]:%m-%d}", fontsize=10 * scale, fontweight="bold")
        ax.set_xticks([])
        if chunk:
            ax.set_xlim(chunk[0], chunk[-1])
        ax.set_ylabel("vehicles", fontsize=10 * scale)
        ax.tick_params(labelleft=True)
        ax.tick_params(labelsize=8 * scale, pad=2 * scale)
        ax.grid(True, axis="y", alpha=0.35)
    fig.suptitle(sample.series[0].name, fontsize=11 * scale, fontweight="bold", y=0.98)
    return [_save(fig, dpi=dpi, fmt=fmt)]


def _save(fig, dpi: int, fmt: str) -> ChartImage:
    fmt = fmt.lower()
    buf = io.BytesIO()
    if fmt in ("jpeg", "jpg"):
        fig.savefig(buf, format="JPEG", dpi=dpi, bbox_inches="tight", pil_kwargs={"quality": 95})
        mime = "image/jpeg"
    elif fmt == "png":
        fig.savefig(buf, format="PNG", dpi=dpi, bbox_inches="tight")
        mime = "image/png"
    else:
        plt.close(fig)
        raise ValueError(f"fmt 은 jpeg 또는 png: {fmt}")
    plt.close(fig)
    return ChartImage(buf.getvalue(), mime)
