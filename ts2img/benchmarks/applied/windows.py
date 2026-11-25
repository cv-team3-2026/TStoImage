"""다음 날 수준 문항.

보여주는 값: 목표일 직전 4주, 672시간.
정답: 목표일 24시간 평균이 직전 24시간 평균보다 얼마나 다른지 다섯 단계.
경계는 그 4주 안의 하루 단위 변화 크기로 정한다. 미래 값은 경계에 쓰지 않는다.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

HISTORY_DAYS = 28  # 직전 4주. 같은 요일이 네 번 보인다
HISTORY = HISTORY_DAYS * 24
HORIZON = 24
DAY = 24
TARGET_N = 90  # 교통량은 결측이 있어 4주가 이어진 날이 196일뿐이다. 간격 2일로 세 데이터가 같이 채우는 수가 90이다
SEED = 0
SCALE_FLOOR = 0.02  # 상대 변화. 이보다 조용한 구간은 경계가 0 으로 붙지 않게 한다


@dataclass(frozen=True)
class Window:
    target_date: date
    start: datetime
    history: tuple[float, ...]
    ref_mean: float
    future_mean: float
    scale: float
    lo: float          # 퍼센트, 소수 1자리. prompt 와 같은 경계
    hi: float
    answer: str
    naive_week: str


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    mid = n // 2
    if n % 2:
        return xs[mid]
    return 0.5 * (xs[mid - 1] + xs[mid])


def _day_means(values: list[float]) -> list[float]:
    return [sum(values[i * DAY : (i + 1) * DAY]) / DAY for i in range(HISTORY // DAY)]


def typical_scale(day_means: list[float]) -> float:
    """보여주는 구간 안에서 하루 평균이 전날 대비 얼마나 움직이는지의 중앙값."""
    rels = []
    for prev, cur in zip(day_means, day_means[1:]):
        if prev == 0 or not math.isfinite(prev) or not math.isfinite(cur):
            continue
        rels.append(abs((cur - prev) / abs(prev)))
    if not rels:
        return SCALE_FLOOR
    return max(_median(rels), SCALE_FLOOR)


def thresholds(scale: float) -> tuple[float, float]:
    """(lo, hi) 퍼센트. prompt 에 적는 소수 1자리와 같은 값으로 라벨을 가른다."""
    lo = round(0.5 * scale * 100, 1)
    hi = round(1.5 * scale * 100, 1)
    if hi <= lo:
        hi = round(lo + 0.1, 1)
    return lo, hi


def classify(rel_pct: float, lo: float, hi: float) -> str:
    """rel_pct = (다음 - 기준) / |기준| * 100."""
    if rel_pct < -hi:
        return "A"
    if rel_pct < -lo:
        return "B"
    if rel_pct <= lo:
        return "C"
    if rel_pct <= hi:
        return "D"
    return "E"


def _rel_pct(new: float, old: float) -> float | None:
    if old == 0 or not math.isfinite(old) or not math.isfinite(new):
        return None
    return (new - old) / abs(old) * 100


def _make(origin: datetime, target: date, history: list[float], future: list[float]) -> Window | None:
    means = _day_means(history)
    ref = means[-1]
    fut = sum(future) / len(future)
    rel = _rel_pct(fut, ref)
    if rel is None:
        return None
    scale = typical_scale(means)
    lo, hi = thresholds(scale)
    # 직전 같은 요일(목표일 7일 전). 4주 창의 첫날이 아니다.
    week = _rel_pct(means[-7], ref)
    if week is None:
        return None
    return Window(
        target_date=target,
        start=origin,
        history=tuple(history),
        ref_mean=ref,
        future_mean=fut,
        scale=scale,
        lo=lo,
        hi=hi,
        answer=classify(rel, lo, hi),
        naive_week=classify(week, lo, hi),
    )


def build_windows(times: list[datetime], values: list[float]) -> list[Window]:
    """매 시각이 1시간 간격으로 이어진 날만 문항 후보로 둔다."""
    lookup = {}
    for t, v in zip(times, values):
        if math.isfinite(v):
            lookup[t] = v
    out = []
    for day in sorted({t.date() for t in lookup}):
        origin = datetime(day.year, day.month, day.day) - timedelta(days=HISTORY_DAYS)
        hist, fut = [], []
        ok = True
        for i in range(HISTORY):
            t = origin + timedelta(hours=i)
            if t not in lookup:
                ok = False
                break
            hist.append(lookup[t])
        if not ok:
            continue
        for i in range(HISTORY, HISTORY + HORIZON):
            t = origin + timedelta(hours=i)
            if t not in lookup:
                ok = False
                break
            fut.append(lookup[t])
        if not ok:
            continue
        w = _make(origin, day, hist, fut)
        if w is not None:
            out.append(w)
    return out


def select_windows(windows: list[Window], n: int = TARGET_N, seed: int = SEED) -> tuple[list[Window], int]:
    """월 × 평일/주말 층을 돌면서 뽑는다.

    예측일은 서로 2일 이상 떨어지게 하고, 그게 모자라면 1일, 그래도 모자라면 간격 없이 채운다.
    돌려주는 간격은 실제로 채울 때 쓴 가장 작은 간격이다.
    """
    rng = random.Random(seed)
    strata: dict[tuple, list[Window]] = {}
    for w in windows:
        key = (w.target_date.month, w.target_date.weekday() >= 5)
        strata.setdefault(key, []).append(w)
    keys = sorted(strata)
    for k in keys:
        rng.shuffle(strata[k])
    remaining = {k: list(strata[k]) for k in keys}
    picked: list[Window] = []
    used_gap = 0
    for gap in (2, 1, 0):
        used_gap = gap
        while len(picked) < n:
            moved = False
            for k in keys:
                bucket = remaining[k]
                for i, w in enumerate(bucket):
                    if all(abs((w.target_date - p.target_date).days) >= gap for p in picked):
                        picked.append(bucket.pop(i))
                        moved = True
                        break
                if len(picked) >= n:
                    break
            if not moved:
                break
        if len(picked) >= n:
            break
    picked.sort(key=lambda w: (w.target_date, w.start))
    return picked, used_gap
