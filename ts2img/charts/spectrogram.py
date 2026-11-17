"""각 series 의 짧은 구간 주파수 세기를 로그 스케일로 그린다.

실제 샘플링 주기가 없어서 주파수 눈금은 bin 번호다.
yaml 예: {use: spectrogram, nperseg: 64}
"""
import matplotlib.pyplot as plt
import numpy as np

from ts2img.charts._format import series_of
from ts2img.charts.base import fig_to_image

VERSION = 1


def _magnitude(values: np.ndarray, nperseg: int) -> np.ndarray:
    values = values - values.mean()
    if len(values) < 8:
        values = np.pad(values, (0, 8 - len(values)))
    nperseg = int(nperseg)
    nperseg = min(nperseg, len(values))
    if nperseg % 2:
        nperseg -= 1
    nperseg = max(4, nperseg)
    hop = max(1, nperseg // 4)
    window = np.hanning(nperseg)
    frames = []
    for start in range(0, len(values) - nperseg + 1, hop):
        frame = values[start : start + nperseg] * window
        frames.append(np.abs(np.fft.rfft(frame)))
    mag = np.stack(frames, axis=1) if frames else np.abs(np.fft.rfft(values))[:, None]
    return np.log1p(mag)


def render(sample, nperseg: int = 64, dpi: int = 100, fmt: str = "jpeg"):
    rows = series_of(sample) or [("series_0", np.zeros(8))]
    n = len(rows)
    fig, axes = plt.subplots(n, 1, figsize=(6, 2.4 * n), squeeze=False)
    for ax, (name, values) in zip(axes[:, 0], rows):
        mag = _magnitude(values, nperseg)
        im = ax.imshow(mag, aspect="auto", origin="lower", cmap="magma", interpolation="nearest")
        ax.set_title(name, fontsize=9)
        ax.set_xlabel("Frame")
        ax.set_ylabel("Frequency bin")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return [fig_to_image(fig, dpi=dpi, fmt=fmt)]
