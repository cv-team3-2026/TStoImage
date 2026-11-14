"""chart 공통 형식과 도우미.

chart 모듈 계약:
    VERSION = 1                               # 같은 params 로 그림이 달라지게 고치면 올린다
    def render(sample, **params) -> list[ChartImage] | None
None 을 돌려주면 이미지 없이 보낸다. 2장 이상이면 여러 장을 보낸다.
"""
from __future__ import annotations

import hashlib
import io
import threading
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")  # 화면 없이 그린다
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

# pyplot 은 thread-safe 하지 않다. 그리는 구간은 이 lock 으로 감싼다
RENDER_LOCK = threading.RLock()

_MIME = {"jpeg": "image/jpeg", "jpg": "image/jpeg", "png": "image/png"}


@dataclass
class ChartImage:
    data: bytes
    mime: str = "image/jpeg"
    caption: str | None = None   # 있으면 이미지 앞에 text 로 같이 보낸다

    def pil(self) -> Image.Image:
        return Image.open(io.BytesIO(self.data))

    @property
    def size(self) -> tuple[int, int]:
        return self.pil().size

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.data).hexdigest()[:16]

    @property
    def ext(self) -> str:
        return "png" if self.mime == "image/png" else "jpg"


def fig_to_image(fig, *, dpi: int = 100, fmt: str = "jpeg", caption: str | None = None) -> ChartImage:
    """matplotlib figure 를 ChartImage 로 바꾸고 figure 를 닫는다. 기본값은 공식 설정(JPEG, 100dpi, tight)."""
    fmt = fmt.lower()
    if fmt not in _MIME:
        raise ValueError(f"fmt 은 jpeg 또는 png: {fmt}")
    buf = io.BytesIO()
    fig.savefig(buf, format="JPEG" if fmt in ("jpeg", "jpg") else "PNG", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return ChartImage(buf.getvalue(), _MIME[fmt], caption)


def pil_to_image(img: Image.Image, *, fmt: str = "png", caption: str | None = None, quality: int = 95) -> ChartImage:
    fmt = fmt.lower()
    buf = io.BytesIO()
    if fmt in ("jpeg", "jpg"):
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
    else:
        img.save(buf, format="PNG")
    return ChartImage(buf.getvalue(), _MIME[fmt], caption)
