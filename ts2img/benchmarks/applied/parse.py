"""시간별 시계열 CSV 를 읽는다. 15분 값은 시간 평균으로 합친다."""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_TIME_FMTS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
)
_DATE_FMTS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y.%m.%d")
_HOUR_COL = re.compile(r"^(\d{1,2})시?$")


def norm_key(key: str) -> str:
    key = key.replace("\ufeff", "").strip().lower()
    key = re.sub(r"\(.*?\)", "", key)
    return re.sub(r"[^a-z0-9가-힣]", "", key)


def read_rows(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        raise ValueError(f"엑셀 파일은 CSV UTF-8 로 저장해 주세요: {path}")
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "cp949", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text or not text.strip():
        raise ValueError(f"빈 파일입니다: {path}")
    head = text.splitlines()[0]
    delim = max([",", "\t", ";"], key=head.count)
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    if not rows:
        raise ValueError(f"데이터 행이 없습니다: {path}")
    return rows


def _cmap(row: dict[str, str]) -> dict[str, str]:
    return {norm_key(k): k for k in row if k is not None}


def _pick(cmap: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in cmap:
            return cmap[name]
    return None


def to_float(text: str) -> float | None:
    s = (text or "").strip().replace(" ", "").replace(",", "")
    if s.lower() in {"", "-", "nan", "none", "null"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_datetime(text: str) -> datetime | None:
    s = (text or "").strip()
    if not s:
        return None
    for fmt in _TIME_FMTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_date(text: str, dayfirst: bool) -> datetime | None:
    s = (text or "").strip()
    fmts = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d") if dayfirst else _DATE_FMTS
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def to_hourly(pairs: list[tuple[datetime, float]]) -> tuple[list[datetime], list[float]]:
    """같은 시계 시간에 모인 값은 평균한다. 분·초는 그 시각의 시로 내린다."""
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for t, v in pairs:
        buckets[t.replace(minute=0, second=0, microsecond=0)].append(v)
    times = sorted(buckets)
    return times, [sum(buckets[t]) / len(buckets[t]) for t in times]


def _pairs_from_long(rows: list[dict[str, str]], time_key: str, value_key: str) -> list[tuple[datetime, float]]:
    out = []
    for row in rows:
        t = parse_datetime(row.get(time_key, ""))
        v = to_float(row.get(value_key, ""))
        if t is not None and v is not None:
            out.append((t, v))
    return out


def parse_metro(path: Path) -> tuple[list[datetime], list[float]]:
    rows = read_rows(path)
    cmap = _cmap(rows[0])
    time_key = _pick(cmap, ("datetime", "timestamp"))
    value_key = _pick(cmap, ("trafficvolume",))
    if not time_key or not value_key:
        raise ValueError(f"Metro CSV 에서 date_time, traffic_volume 열을 찾지 못했습니다: {path}")
    pairs = _pairs_from_long(rows, time_key, value_key)
    if not pairs:
        raise ValueError(f"Metro CSV 에서 읽은 시각이 없습니다: {path}")
    return to_hourly(pairs)


def parse_seoul(path: Path) -> tuple[list[datetime], list[float]]:
    rows = read_rows(path)
    cmap = _cmap(rows[0])
    date_key = _pick(cmap, ("date",))
    hour_key = _pick(cmap, ("hour",))
    value_key = _pick(cmap, ("rentedbikecount",))
    if not date_key or not hour_key or not value_key:
        raise ValueError(f"Seoul Bike CSV 에서 Date, Hour, Rented Bike Count 열을 찾지 못했습니다: {path}")
    pairs = []
    for row in rows:
        day = parse_date(row.get(date_key, ""), dayfirst=True)
        hour = to_float(row.get(hour_key, ""))
        v = to_float(row.get(value_key, ""))
        if day is None or hour is None or v is None:
            continue
        pairs.append((day + timedelta(hours=int(hour)), v))
    if not pairs:
        raise ValueError(f"Seoul Bike CSV 에서 읽은 시각이 없습니다: {path}")
    return to_hourly(pairs)


def parse_seoul_weather(path: Path) -> tuple[list[datetime], dict[str, list[float]]]:
    """대여량·기온·강수량·공휴일·운영일을 시간별로 읽는다. holiday/functioning 은 0/1."""
    rows = read_rows(path)
    cmap = _cmap(rows[0])
    date_key = _pick(cmap, ("date",))
    hour_key = _pick(cmap, ("hour",))
    value_key = _pick(cmap, ("rentedbikecount",))
    temp_key = _pick(cmap, ("temperature", "temperaturec"))
    rain_key = _pick(cmap, ("rainfall", "rainfallmm"))
    holiday_key = _pick(cmap, ("holiday",))
    func_key = _pick(cmap, ("functioningday",))
    if not date_key or not hour_key or not value_key or not temp_key or not rain_key:
        raise ValueError(
            f"Seoul Bike CSV 에서 Date, Hour, Rented Bike Count, Temperature, Rainfall 열을 찾지 못했습니다: {path}"
        )
    buckets: dict[datetime, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        day = parse_date(row.get(date_key, ""), dayfirst=True)
        hour = to_float(row.get(hour_key, ""))
        rent = to_float(row.get(value_key, ""))
        temp = to_float(row.get(temp_key, ""))
        rain = to_float(row.get(rain_key, ""))
        if day is None or hour is None or rent is None or temp is None or rain is None:
            continue
        t = day + timedelta(hours=int(hour))
        buckets[t]["rentals"].append(rent)
        buckets[t]["temperature"].append(temp)
        buckets[t]["rainfall"].append(rain)
        if holiday_key:
            hol = (row.get(holiday_key, "") or "").strip().lower()
            buckets[t]["holiday"].append(0.0 if hol in {"no holiday", "no", "0"} else 1.0)
        if func_key:
            fn = (row.get(func_key, "") or "").strip().lower()
            buckets[t]["functioning"].append(1.0 if fn in {"yes", "1", "y"} else 0.0)
    if not buckets:
        raise ValueError(f"Seoul Bike CSV 에서 읽은 시각이 없습니다: {path}")
    times = sorted(buckets)
    cols = {
        "rentals": [sum(buckets[t]["rentals"]) / len(buckets[t]["rentals"]) for t in times],
        "temperature": [sum(buckets[t]["temperature"]) / len(buckets[t]["temperature"]) for t in times],
        "rainfall": [sum(buckets[t]["rainfall"]) / len(buckets[t]["rainfall"]) for t in times],
        "holiday": [
            (sum(buckets[t]["holiday"]) / len(buckets[t]["holiday"])) if buckets[t]["holiday"] else 0.0
            for t in times
        ],
        "functioning": [
            (sum(buckets[t]["functioning"]) / len(buckets[t]["functioning"])) if buckets[t]["functioning"] else 1.0
            for t in times
        ],
    }
    return times, cols


def _wide_pairs(rows: list[dict[str, str]], date_key: str) -> list[tuple[datetime, float]] | None:
    hour_cols: list[tuple[int, str]] = []
    for key in rows[0]:
        m = _HOUR_COL.match(norm_key(key))
        if m:
            hour_cols.append((int(m.group(1)), key))
    if len(hour_cols) < 20:
        return None
    numbers = {n for n, _ in hour_cols}
    end_of_day = 0 not in numbers and max(numbers) >= 24
    pairs = []
    for row in rows:
        day = parse_date(row.get(date_key, ""), dayfirst=False) or parse_date(row.get(date_key, ""), dayfirst=True)
        if day is None:
            continue
        for n, key in hour_cols:
            v = to_float(row.get(key, ""))
            if v is None:
                continue
            hour = n - 1 if end_of_day else n
            if 0 <= hour <= 23:
                pairs.append((day + timedelta(hours=hour), v))
    return pairs


def parse_kpx(path: Path) -> tuple[list[datetime], list[float]]:
    rows = read_rows(path)
    cmap = _cmap(rows[0])
    value_key = _pick(cmap, ("loadmw", "load", "demand", "powerdemand", "전력수요량", "전력수요", "수요", "전력사용량"))
    time_key = _pick(cmap, ("timestamp", "datetime", "일시", "기준일시"))
    date_key = _pick(cmap, ("date", "날짜", "일자", "기준일"))
    hour_key = _pick(cmap, ("hour", "시", "시간", "시간대"))
    pairs: list[tuple[datetime, float]] = []
    if date_key and hour_key and value_key:
        for row in rows:
            day = parse_date(row.get(date_key, ""), dayfirst=False) or parse_date(row.get(date_key, ""), dayfirst=True)
            hour = to_float(row.get(hour_key, ""))
            v = to_float(row.get(value_key, ""))
            if day is None or hour is None or v is None:
                continue
            pairs.append((day + timedelta(hours=int(hour)), v))
    elif time_key and value_key:
        pairs = _pairs_from_long(rows, time_key, value_key)
    else:
        if not date_key:
            raise ValueError(
                f"KPX CSV 에서 시각 열과 수요 열을 찾지 못했습니다: {path}\n"
                "긴 표는 timestamp, load_mw. 넓은 표는 날짜 열과 1시–24시 열."
            )
        wide = _wide_pairs(rows, date_key)
        if wide is None:
            raise ValueError(f"KPX CSV 형식을 읽지 못했습니다: {path}")
        pairs = wide
    if not pairs:
        raise ValueError(f"KPX CSV 에서 읽은 시각이 없습니다: {path}")
    return to_hourly(pairs)
