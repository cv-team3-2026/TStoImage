"""실제 시계열 3개. 데이터셋마다 벤치마크를 나눠 정확도를 합치지 않는다.

metro, seoul_bike 는 UCI 에서 받는다. kpx 는 사용자가 CSV 를 둔다.
문항 정의가 바뀌면 version 을 올린다.
"""
from __future__ import annotations

import gzip
import shutil
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path

from ts2img.benchmarks.applied import parse
from ts2img.benchmarks.applied import prompts
from ts2img.benchmarks.applied.windows import (
    HISTORY_DAYS,
    SEED,
    TARGET_N,
    Window,
    build_windows,
    select_windows,
)
from ts2img.benchmarks.base import Benchmark, Sample, Score, Selection, Series  # noqa: F401
from ts2img.benchmarks.tsrbench import scoring
from ts2img.paths import data_dir

UCI = {
    "metro": {
        "url": "https://archive.ics.uci.edu/static/public/492/metro+interstate+traffic+volume.zip",
        "csv": "Metro_Interstate_Traffic_Volume.csv",
    },
    "seoul_bike": {
        "url": "https://archive.ics.uci.edu/static/public/560/seoul+bike+sharing+demand.zip",
        "csv": "SeoulBikeData.csv",
    },
}

SPEC = {
    "metro": {
        "quantity": "hourly interstate traffic volume",
        "unit": "vehicles",
        "series": "Traffic volume",
        "parse": parse.parse_metro,
    },
    "seoul_bike": {
        "quantity": "hourly city-wide public bike rentals",
        "unit": "bikes",
        "series": "Bike rentals",
        "parse": parse.parse_seoul,
    },
    "kpx": {
        "quantity": "hourly national electricity demand",
        "unit": "MW",
        "series": "Electricity demand (MW)",
        "parse": parse.parse_kpx,
    },
}


def kpx_missing_message(path: Path) -> str:
    return (
        "KPX 시간별 전력수요 CSV 가 없습니다.\n"
        f"저장 위치: {path}\n"
        "형식: timestamp, load_mw (1시간 간격, 한국 표준시). "
        "15분 값을 넣으면 시간 평균으로 합칩니다. "
        "날짜 열과 1시–24시 열로 된 넓은 표도 읽습니다. 1시는 00:00–01:00 으로 둡니다. "
        "엑셀 파일은 CSV UTF-8 로 저장해 주세요.\n"
        "받는 곳: 공공데이터포털 파일데이터. 로그인 없이 CSV 를 받으면 됩니다.\n"
        "https://www.data.go.kr/data/15065266/fileData.do\n"
        "페이지 위쪽의 CSV 다운로드입니다. 열은 날짜, 1시–24시 이고 지금 로더가 그대로 읽습니다.\n"
        "가능하면 1년 이상을 두세요. 이 파일 없이 교통량과 따릉이만 돌리려면:\n"
        "python -m ts2img run applied_forecast --benchmarks applied_metro,applied_seoul --auto-serve"
    )


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ts2img-applied"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _extract(zip_path: Path, folder: Path) -> None:
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(folder)
    for gz in folder.rglob("*.gz"):
        out = gz.with_suffix("")
        with gzip.open(gz, "rb") as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)


class _Applied(Benchmark):
    dataset = ""
    version = 2
    revision = "next-day-level-v2"

    def units(self) -> list[str]:
        return [self.dataset]

    def leaf_tasks(self) -> list[str]:
        return [self.dataset]

    def select(self, path: str) -> list[Selection]:
        path = path.strip("/")
        if path in ("", self.dataset):
            return [Selection(self.dataset)]
        raise KeyError(f"{self.name} 에 없는 task: {path!r} (사용 가능: {self.dataset})")

    def root(self) -> Path:
        return data_dir() / "applied"

    def csv_path(self, unit: str | None = None) -> Path:
        unit = unit or self.dataset
        if unit == "kpx":
            return self.root() / "kpx" / "hourly.csv"
        spec = UCI[unit]
        return self.root() / unit / spec["csv"]

    def has_data(self, unit: str) -> bool:
        p = self.csv_path(unit)
        return p.is_file() and p.stat().st_size > 0

    def n_samples(self, unit: str) -> int | None:
        if not self.has_data(unit):
            return None
        return len(self.load(unit))

    def ensure_data(self, units: list[str] | None = None) -> None:
        from ts2img import ui

        for unit in units or self.units():
            if self.has_data(unit):
                continue
            if unit == "kpx":
                raise FileNotFoundError(kpx_missing_message(self.csv_path(unit)))
            spec = UCI[unit]
            folder = self.root() / unit
            folder.mkdir(parents=True, exist_ok=True)
            ui.info(f"다운로드: {spec['url']}")
            zip_path = folder / "source.zip"
            try:
                _download(spec["url"], zip_path)
                _extract(zip_path, folder)
            except Exception as e:
                raise RuntimeError(f"{unit} 다운로드 실패: {e}") from e
            if not self.has_data(unit):
                raise RuntimeError(f"받은 압축에서 {spec['csv']} 를 찾지 못했습니다: {folder}")
            ui.ok(f"데이터 준비 완료: {self.csv_path(unit)}")

    @lru_cache(maxsize=None)
    def load(self, unit: str) -> list[Sample]:
        from collections import Counter

        from ts2img import ui

        self.ensure_data([unit])
        spec = SPEC[unit]
        times, values = spec["parse"](self.csv_path(unit))
        windows = build_windows(times, values)
        picked, gap = select_windows(windows, TARGET_N, SEED)
        if not picked:
            raise RuntimeError(
                f"{unit}: 빈틈 없이 이어진 {HISTORY_DAYS + 1}일이 없습니다. 시간 간격과 결측을 확인하세요."
            )
        counts = Counter(w.answer for w in picked)
        order = " ".join(f"{k} {counts[k]}" for k in "ABCDE" if counts[k])
        ui.info(f"{self.name}: {len(picked)}문항, 예측일 간격 {gap}일, 정답 {order}")
        return [_sample(unit, i, w, spec, gap) for i, w in enumerate(picked)]

    def prompt(self, sample: Sample, modality: str, opts: dict) -> prompts.PromptSpec:
        return prompts.build(sample, modality)

    def score(self, sample: Sample, response: str) -> Score:
        return scoring.score(sample.answer, response)

    def options(self, sample: Sample) -> list[str]:
        return list(prompts.LABELS)


def _sample(unit: str, idx: int, w: Window, spec: dict, gap: int) -> Sample:
    question = prompts.question_text(spec["quantity"], spec["unit"], w.start, w.ref_mean, w.scale, w.lo, w.hi)
    return Sample(
        id=f"{unit}#{w.target_date.isoformat()}",
        unit=unit,
        task=unit,
        idx=idx,
        question=question,
        answer=w.answer,
        series=[Series(spec["series"], list(w.history))],
        choices=list(prompts.LABELS),
        raw={
            "target_date": w.target_date.isoformat(),
            "ref_mean": w.ref_mean,
            "future_mean": w.future_mean,
            "scale": w.scale,
            "lo": w.lo,
            "hi": w.hi,
            "naive_week": w.naive_week,
            "naive_persist": "C",
            "min_gap_days": gap,
            "seed": SEED,
        },
    )


class AppliedMetro(_Applied):
    name = "applied_metro"
    dataset = "metro"


class AppliedSeoul(_Applied):
    name = "applied_seoul"
    dataset = "seoul_bike"


class AppliedKpx(_Applied):
    name = "applied_kpx"
    dataset = "kpx"


class AppliedMetroPeak(_Applied):
    """내일 95% 피크 시간 집합. 채점은 F1."""

    name = "applied_metro_peak"
    dataset = "metro"
    version = 7
    revision = "peak-hours-v4"

    @lru_cache(maxsize=None)
    def load(self, unit: str) -> list[Sample]:
        from ts2img import ui

        from ts2img.benchmarks.applied.peak import TARGET_N, build_samples

        self.ensure_data([unit])
        times, values = parse.parse_metro(self.csv_path(unit))
        samples, gap = build_samples(times, values, TARGET_N, SEED)
        if not samples:
            raise RuntimeError(f"{unit}: 4주가 빈틈 없이 이어진 날이 없습니다.")
        ui.info(f"{self.name}: {len(samples)}문항, 예측일 간격 {gap}일")
        return samples

    def prompt(self, sample: Sample, modality: str, opts: dict):
        from ts2img.benchmarks.applied.peak import vision_prompt

        if modality != "vision":
            raise ValueError("applied_metro_peak 는 vision 만 씁니다")
        return vision_prompt(sample)

    def score(self, sample: Sample, response: str) -> Score:
        from ts2img.benchmarks.applied.peak import score_hours

        return score_hours(sample.answer, response)

    def options(self, sample: Sample) -> list[str]:
        return [str(h) for h in range(24)]


class AppliedSeoulPeak(_Applied):
    """따릉이 재배치 피크 시각 집합. 채점은 F1. text / vision."""

    name = "applied_seoul_peak"
    dataset = "seoul_bike"
    version = 1
    revision = "seoul-peak-v1"

    @lru_cache(maxsize=None)
    def load(self, unit: str) -> list[Sample]:
        from ts2img import ui

        from ts2img.benchmarks.applied.seoul_peak import TARGET_N, build_samples, naive_f1

        self.ensure_data([unit])
        times, cols = parse.parse_seoul_weather(self.csv_path(unit))
        samples, gap, stats = build_samples(
            times,
            cols["rentals"],
            cols["temperature"],
            cols["rainfall"],
            cols["holiday"],
            cols["functioning"],
            TARGET_N,
            SEED,
        )
        if not samples:
            raise RuntimeError(f"{unit}: 7+1일이 빈틈 없이 이어진 날이 없습니다.")
        week = naive_f1(samples, "naive_hours_week")
        yest = naive_f1(samples, "naive_hours_yesterday")
        ui.info(
            f"{self.name}: {stats['n']}문항(전환일 {stats['picked_hard']}/{stats['n']}), "
            f"간격 {gap}일, 7일전 F1 {week:.1%}, 어제 F1 {yest:.1%}"
        )
        return samples

    def prompt(self, sample: Sample, modality: str, opts: dict):
        from ts2img.benchmarks.applied.seoul_peak import build_prompt

        return build_prompt(sample, modality)

    def score(self, sample: Sample, response: str) -> Score:
        from ts2img.benchmarks.applied.seoul_peak import score_seoul_hours

        return score_seoul_hours(sample.answer, response)

    def options(self, sample: Sample) -> list[str]:
        return [str(h) for h in range(24)]
