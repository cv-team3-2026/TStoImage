"""따릉이 피크 예측용 가로 2패널 차트.

왼쪽: 과거 대여량(TSRBench 스타일 파란 선) + 임계 빨간 점선 + 예측일 회색 음영(대여량 없음)
오른쪽: 과거+예보 기온(선)과 강수(막대). 같은 회색 음영.
perception 에서 이득이 있던 scale=3, 가로(row) 배치를 기본으로 둔다.

yaml 예: {use: bike_peak, scale: 3}
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from ts2img.charts.base import fig_to_image

VERSION = 1


def render(sample, scale: float = 3.0, dpi: int = 100, fmt: str = "jpeg"):
    thr = float(sample.raw.get("threshold", 1000))
    hist = int(sample.raw.get("history_hours", 168))
    horizon = int(sample.raw.get("horizon_hours", 24))
    total = hist + horizon

    rentals = np.asarray(sample.series[0].values, dtype=float)
    temp = np.asarray(sample.series[1].values, dtype=float) if len(sample.series) > 1 else None
    rain = np.asarray(sample.series[2].values, dtype=float) if len(sample.series) > 2 else None
    if temp is not None and len(temp) < total:
        temp = np.pad(temp, (0, total - len(temp)), constant_values=np.nan)
    if rain is not None and len(rain) < total:
        rain = np.pad(rain, (0, total - len(rain)), constant_values=np.nan)

    k = float(scale)
    fig, axes = plt.subplots(1, 2, figsize=(6.4 * k, 2.4 * k), sharex=False)
    ax_r, ax_w = axes

    x_hist = np.arange(len(rentals))
    ax_r.plot(x_hist, rentals, color="blue", linewidth=2)
    ax_r.axhline(thr, color="red", linestyle="--", linewidth=1.5, label=f"threshold {thr:.0f}")
    ax_r.axvspan(hist - 0.5, total - 0.5, color="#9e9e9e", alpha=0.25, zorder=0)
    ax_r.set_xlim(-0.5, total - 0.5)
    ax_r.set_title("Bike rentals", fontsize=10, fontweight="bold")
    ax_r.set_xlabel("Time / Index")
    ax_r.set_ylabel("bikes / hour")
    ax_r.grid(True)
    ax_r.spines["top"].set_visible(False)
    ax_r.spines["right"].set_visible(False)
    ax_r.legend(loc="upper left", fontsize=8)

    x_full = np.arange(total)
    if temp is not None:
        ax_w.plot(x_full, temp, color="blue", linewidth=2, label="Temperature (C)")
    if rain is not None:
        ax_rain = ax_w.twinx()
        ax_rain.bar(x_full, rain, color="#4C78A8", alpha=0.35, width=0.8, label="Rainfall (mm)")
        ax_rain.set_ylabel("mm", fontsize=9)
        ax_rain.spines["top"].set_visible(False)
    ax_w.axvspan(hist - 0.5, total - 0.5, color="#9e9e9e", alpha=0.25, zorder=0)
    ax_w.set_xlim(-0.5, total - 0.5)
    ax_w.set_title("Temperature & rainfall (incl. forecast)", fontsize=10, fontweight="bold")
    ax_w.set_xlabel("Time / Index")
    ax_w.set_ylabel("C", fontsize=9)
    ax_w.grid(True, alpha=0.3)
    ax_w.spines["top"].set_visible(False)
    ax_w.spines["right"].set_visible(False)
    ax_w.legend(loc="upper left", fontsize=8)

    fig.tight_layout()
    return [fig_to_image(fig, dpi=dpi, fmt=fmt)]
