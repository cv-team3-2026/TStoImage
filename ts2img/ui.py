"""터미널 / 노트북 출력 도우미 (rich, pyfiglet)."""
from __future__ import annotations

import os
import sys
from typing import Iterable, Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_IN_NOTEBOOK = bool(os.environ.get("COLAB_RELEASE_TAG") or os.environ.get("JPY_PARENT_PID"))


def _make_console() -> Console:
    # Windows 기본 콘솔 encoding(cp949)에서 box 문자가 깨지지 않게 한다
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if _IN_NOTEBOOK:
        # 노트북의 `!` 셀: 색은 쓰되 줄 단위로만 출력한다
        return Console(force_terminal=True, width=120, height=50, highlight=False)
    if not _is_tty():
        # 파일이나 pipe 로 나갈 때: 표가 접히지 않게 넓게 잡는다
        return Console(width=140, height=50, highlight=False)
    return Console(highlight=False)


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    except Exception:
        return False


console = _make_console()


def live_capable() -> bool:
    """진행 바를 제자리에서 갱신할 수 있는 환경인지."""
    return _is_tty() and console.is_terminal and not _IN_NOTEBOOK


def banner(subtitle: str = "") -> None:
    try:
        from pyfiglet import Figlet

        art = Figlet(font="slant").renderText("ts2img").rstrip("\n")
    except Exception:
        art = "ts2img"
    console.print(f"[bold cyan]{art}[/]")
    if subtitle:
        console.print(f"[dim]{subtitle}[/]\n")


def panel(body: str, title: str = "", style: str = "cyan") -> None:
    console.print(Panel(body, title=title or None, border_style=style, expand=False))


def info(msg: str) -> None:
    console.print(f"[cyan]>[/] {msg}")


def ok(msg: str) -> None:
    console.print(f"[green]OK[/] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]주의[/] {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]오류[/] {msg}")


def table(title: str, columns: Sequence[str], rows: Iterable[Sequence], *, right: Sequence[int] = ()) -> None:
    rows = [["" if v is None else str(v) for v in r] for r in rows]
    # 값이 하나도 없는 열은 뺀다 (예: 비고)
    keep = [i for i in range(len(columns)) if not rows or any(r[i] != "" for r in rows)]
    t = Table(title=title or None, box=box.ROUNDED, header_style="bold", title_justify="left")
    for i in keep:
        t.add_column(columns[i], justify="right" if i in right else "left", overflow="fold")
    for r in rows:
        t.add_row(*[r[i] for i in keep])
    console.print(t)


def kv_table(title: str, items: Iterable[tuple[str, object]]) -> None:
    t = Table(title=title or None, box=box.ROUNDED, show_header=False, title_justify="left")
    t.add_column("k", style="bold")
    t.add_column("v", overflow="fold")
    for k, v in items:
        t.add_row(str(k), "" if v is None else str(v))
    console.print(t)


def fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds != seconds or seconds < 0:
        return "?"
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def fmt_pct(x: float | None, digits: int = 1) -> str:
    return "-" if x is None else f"{100 * x:.{digits}f}"


def bar(frac: float, width: int = 24) -> str:
    frac = min(max(frac, 0.0), 1.0)
    n = int(round(frac * width))
    return "█" * n + "░" * (width - n)

