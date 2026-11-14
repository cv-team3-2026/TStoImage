"""실험 실행기.

- cell 마다 run 폴더 하나. 이미 끝난 문항은 건너뛰고 남은 문항만 실행한다 (재개).
- 문항이 끝날 때마다 predictions.jsonl 에 바로 기록한다.
- 진행 상황은 화면, run.log, status.json 에 같이 남긴다.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ts2img import cost, sysinfo, ui
from ts2img.benchmarks import get_benchmark
from ts2img.benchmarks.base import Sample
from ts2img.config import Cell, Experiment, expand, load_pricing
from ts2img.methods import get_method
from ts2img.methods.base import RunContext
from ts2img.models.client import ChatClient, FatalModelError
from ts2img.paths import experiment_dir
from ts2img.report.stats import summarize
from ts2img.store import FINAL_STATUS, RunStore, now_iso, read_json, write_json

log = logging.getLogger("ts2img")


@dataclass
class RunOptions:
    budget_usd: float | None = None
    auto_serve: bool = False
    dry_run: bool = False
    sync_dir: Path | None = None
    force: bool = False
    retry_overflow: bool = False  # context_overflow 로 끝난 문항을 다시 보낸다 (외부 서버의 한도가 바뀌었을 때)
    capture_n: int = 3          # run 마다 요청 전문을 남길 문항 수
    chart_samples_n: int = 8    # run 마다 chart 이미지를 남길 문항 수


@dataclass
class CellPlan:
    cell: Cell
    samples: list[Sample]
    records: dict[str, dict]          # 선택된 문항 중 이미 기록이 있는 것
    pending: list[Sample]
    state: str = "pending"            # pending | running | done | failed | stopped
    error: str | None = None
    session_done: int = 0

    def counts(self) -> dict:
        s = summarize(list(self.records.values()))
        return {"total": len(self.samples), "done": sum(1 for r in self.records.values() if r.get("status") in FINAL_STATUS), **s}


def run_process_alive(pid) -> bool:
    """status.json 의 pid 가 지금도 돌고 있는 ts2img 실행인지.

    pid 만 보면 안 된다: Drive 에서 복원한 기록의 pid 를 새 VM 의 다른 프로세스가 쓰고 있을 수 있다.
    """
    try:
        import psutil

        p = psutil.Process(int(pid))
        if p.status() == psutil.STATUS_ZOMBIE:
            return False
        return any("ts2img" in part for part in p.cmdline())
    except Exception:
        return False


def select_samples(cell: Cell) -> list[Sample]:
    """cell 에서 이번 실험이 다루는 문항. 선택은 run hash 와 무관하다."""
    samples = get_benchmark(cell.benchmark).load(cell.unit)
    if cell.subtasks:
        samples = [s for s in samples if s.task in cell.subtasks]
    if cell.exp.limit:
        samples = samples[: cell.exp.limit]
    return samples


def is_done(rec: dict | None, cell: Cell, retry_overflow: bool = False) -> bool:
    """이 문항을 다시 보내지 않아도 되는지."""
    status = (rec or {}).get("status")
    if status == "ok":
        return True
    if status == "context_overflow":
        # 같은 한도에서는 다시 해도 같다. 한도가 바뀌었거나 사용자가 요청하면 다시 시도한다
        return not retry_overflow and rec.get("ctx_limit") == cell.model.context_limit
    return False


def make_plans(exp: Experiment, cells: list[Cell] | None = None, retry_overflow: bool = False) -> list[CellPlan]:
    cells = cells if cells is not None else expand(exp)
    needed: dict[str, set[str]] = {}
    for c in cells:
        needed.setdefault(c.benchmark, set()).add(c.unit)
    for bench, units in needed.items():
        get_benchmark(bench).ensure_data(sorted(units))
    plans = []
    for c in cells:
        samples = select_samples(c)
        ids = {s.id for s in samples}
        records = {i: r for i, r in RunStore(c.run_dir).load().items() if i in ids}
        pending = [s for s in samples if not is_done(records.get(s.id), c, retry_overflow)]
        plans.append(CellPlan(c, samples, records, pending))
    return plans


def cell_columns(c: Cell) -> tuple[str, str, str, str]:
    """표에 쓰는 cell 표기: (task, model, 입력, chart)."""
    chart = "-" if c.modality == "text" else c.chart.label
    return (f"{c.benchmark}/{c.unit}", c.model.key, c.modality, chart + (f" r{c.repeat}" if c.repeat else ""))


def show_plan(exp: Experiment, plans: list[CellPlan]) -> None:
    rows = []
    for p in plans:
        c = p.cell
        done = len(p.samples) - len(p.pending)
        rows.append((*cell_columns(c), len(p.samples), done, len(p.pending), c.hash))
    ui.table(f"실험 계획: {exp.name}", ["task", "model", "입력", "chart", "문항", "완료", "남음", "hash"], rows, right=(4, 5, 6))
    total = sum(len(p.pending) for p in plans)
    ui.info(f"cell {len(plans)}개, 남은 요청 {total}건 (sampling: {exp.sampling if isinstance(exp.sampling, str) else exp.sampling_params()}, concurrency {exp.concurrency})")


# ---- 진행 표시 -------------------------------------------------------------
class Tracker:
    def __init__(self, exp: Experiment, plans: list[CellPlan], budget: float | None):
        self.exp, self.plans, self.budget = exp, plans, budget
        self.total = sum(len(p.pending) for p in plans)
        self.done = 0
        self.spent = 0.0
        self.t0 = time.time()
        self.state = "running"
        self.current: CellPlan | None = None
        self.status_path = experiment_dir(exp.name) / "status.json"
        self._lock = threading.Lock()
        self._last_status = 0.0
        self._last_line = 0.0
        self._last_log = 0.0
        self._live = None
        if ui.live_capable() and self.total:
            from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

            self._live = Progress(
                TextColumn("{task.description}"), BarColumn(bar_width=28), MofNCompleteColumn(),
                TextColumn("{task.fields[info]}"), TextColumn("경과"), TimeElapsedColumn(),
                TextColumn("남음"), TimeRemainingColumn(), console=ui.console,
            )
            self._live.start()
            self._t_all = self._live.add_task("전체", total=self.total, info="")
            self._t_cell = self._live.add_task("cell", total=1, info="", visible=False)

    def eta(self) -> float | None:
        if not self.done:
            return None
        return (self.total - self.done) * (time.time() - self.t0) / self.done

    def start_cell(self, plan: CellPlan) -> None:
        self.current = plan
        plan.state = "running"
        if self._live:
            self._live.reset(self._t_cell, total=len(plan.pending), visible=True, description="현재", info="")
        self.write_status(force=True)

    def on_record(self, plan: CellPlan, rec: dict, price: dict | None) -> None:
        with self._lock:
            plan.records[rec["id"]] = rec
            plan.session_done += 1
            self.done += 1
            self.spent += cost.cost_of(rec, price)
        if rec.get("status") == "error":
            log.warning("문항 실패 %s: %s", rec["id"], rec.get("error"))
        self._render(plan)
        self.write_status()

    def line(self, plan: CellPlan | None) -> str:
        el = time.time() - self.t0
        rate = self.done / el * 60 if el > 0 else 0
        s = f"전체 {self.done}/{self.total} ({100 * self.done / max(1, self.total):.1f}%)"
        if plan:
            c = plan.counts()
            s += f" | 현재 {plan.session_done}/{len(plan.pending)} 정확도 {ui.fmt_pct(c['acc'])}%"
        s += f" | 경과 {ui.fmt_duration(el)} | 남음 ~{ui.fmt_duration(self.eta())} | {rate:.1f}문항/분"
        if self.budget is not None:
            s += f" | ${self.spent:.3f} / ${self.budget:.2f}"
        return s

    def _render(self, plan: CellPlan) -> None:
        now = time.time()
        if self._live:
            acc = ui.fmt_pct(plan.counts()["acc"]) if now - self._last_line > 1 else None
            self._live.advance(self._t_all)
            if acc is not None:
                self._last_line = now
                self._live.update(self._t_cell, advance=1, info=f"정확도 {acc}%")
            else:
                self._live.advance(self._t_cell)
        elif now - self._last_line > 10:
            self._last_line = now
            ui.console.print(f"[dim]{datetime.now():%H:%M:%S}[/] {self.line(plan)}", soft_wrap=True)
        if now - self._last_log > 30:
            self._last_log = now
            log.info(self.line(plan))

    def status(self) -> dict:
        el = time.time() - self.t0
        cells = []
        for p in self.plans:
            c = p.counts()
            cells.append({"label": p.cell.label, "columns": list(cell_columns(p.cell)), "run_dir": str(p.cell.run_dir),
                          "state": "done" if c["done"] >= c["total"] else p.state,
                          "error": p.error, **{k: c[k] for k in ("total", "done", "n_ok", "n_done", "acc", "n_error", "n_overflow")}})
        return {
            "experiment": self.exp.name, "state": self.state, "pid": os.getpid(),
            "started_at": datetime.fromtimestamp(self.t0).astimezone().isoformat(timespec="seconds"),
            "updated_at": now_iso(), "elapsed_s": round(el, 1), "eta_s": self.eta(),
            "requests_done": self.done, "requests_total": self.total,
            "spent_usd": round(self.spent, 4) if self.budget is not None else None, "budget_usd": self.budget,
            "current": self.current.cell.label if self.current else None,
            "cells": cells,
        }

    def write_status(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_status < 3:
            return
        self._last_status = now
        try:
            write_json(self.status_path, self.status())
        except OSError:
            pass

    def finish(self, state: str) -> None:
        self.state = state
        if self._live:
            self._live.stop()
        self.write_status(force=True)


# ---- 실행 ------------------------------------------------------------------
def _setup_logging(exp_dir: Path) -> None:
    exp_dir.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.INFO)
    log.propagate = False
    for h in list(log.handlers):
        log.removeHandler(h)
    fh = logging.FileHandler(exp_dir / "run.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(fh)


def _server_default_sampling(cell: Cell) -> dict | None:
    """직접 띄우는 모델의 generation_config.json (sampling 을 보내지 않을 때 서버가 쓰는 값). 실패하면 None."""
    serve = cell.model.serve
    if not serve or cell.model.provider != "openai":
        return None
    try:
        import json

        from huggingface_hub import hf_hub_download

        p = hf_hub_download(cell.model.model, "generation_config.json", revision=serve.get("revision"))
        cfg = json.loads(Path(p).read_text(encoding="utf-8"))
        return {k: cfg[k] for k in ("do_sample", "temperature", "top_p", "top_k", "repetition_penalty") if k in cfg}
    except Exception:
        return None


def _write_run_meta(plan: CellPlan, env: dict, endpoint_models: list[str], default_sampling: dict | None) -> None:
    cell = plan.cell
    d = cell.run_dir
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "hash": cell.hash, "label": cell.label, "experiment": cell.exp.name, "updated_at": now_iso(),
        "identity": cell.identity(),
        "endpoint": {
            "base_url": f"(secrets: {cell.model.base_url_env})" if cell.model.base_url_env else cell.model.resolved_base_url(),
            "models": endpoint_models,
            "serve_settings_known": bool(cell.model.serve) or cell.model.provider == "mock",
        },
        "sampling_sent": cell.exp.sampling_params(cell.repeat) or "없음 (서버 기본값 사용)",
        "server_default_sampling": default_sampling,
    }
    write_json(d / "config.json", meta)
    write_json(d / "env.json", env)


def _run_cell(plan: CellPlan, client: ChatClient, tracker: Tracker, opts: RunOptions, stop: threading.Event,
              price: dict | None) -> None:
    cell = plan.cell
    bench = get_benchmark(cell.benchmark)
    method = get_method(cell.exp.method["use"])
    params = {k: v for k, v in cell.exp.method.items() if k != "use"}
    store = RunStore(cell.run_dir)

    # 앞쪽 문항의 chart 이미지와 요청 전문을 예시로 남긴다
    chart_ids = {s.id for s in plan.samples[: opts.chart_samples_n]}
    request_ids = {s.id for s in plan.samples[: opts.capture_n]}
    captured = {r["id"]: r for r in read_json(cell.run_dir / "request_samples.json", [])}
    cap_lock = threading.Lock()

    def capture(sample, req):
        if sample.id not in chart_ids:
            return
        with cap_lock:
            names = []
            for k, im in enumerate(req.images):
                name = f"{sample.idx:05d}_{k}.{im.ext}"
                (cell.run_dir / "chart_samples").mkdir(parents=True, exist_ok=True)
                (cell.run_dir / "chart_samples" / name).write_bytes(im.data)
                names.append(name)
            if sample.id in request_ids:
                kwargs = client.build_kwargs([], response_format=req.response_format,
                                             sampling=cell.exp.sampling_params(cell.repeat), max_tokens=cell.exp.max_tokens)
                kwargs.pop("messages")
                captured[sample.id] = {
                    "id": sample.id, "prompt_text": req.prompt_text,
                    "images": names, "captions": [im.caption for im in req.images], "request": kwargs,
                }
                write_json(cell.run_dir / "request_samples.json", list(captured.values()))

    ctx = RunContext(cell, bench, client, capture)
    consecutive_errors = 0
    limit_errors = max(20, 2 * cell.exp.concurrency)

    def work(sample):
        if stop.is_set():
            return None
        rec = method.run_sample(sample, ctx, **params)
        store.append(rec)  # 결과는 worker 에서 바로 기록한다
        return rec

    log.info("cell 시작: %s (남은 문항 %d) -> %s", cell.label, len(plan.pending), cell.run_dir)
    tracker.start_cell(plan)
    pool = ThreadPoolExecutor(max_workers=max(1, cell.exp.concurrency))
    futures = [pool.submit(work, s) for s in plan.pending]
    try:
        for fut in as_completed(futures):
            rec = fut.result()
            if rec is None:
                continue
            tracker.on_record(plan, rec, price)
            consecutive_errors = consecutive_errors + 1 if rec.get("status") == "error" else 0
            if consecutive_errors >= limit_errors:
                raise FatalModelError(f"요청이 연속 {consecutive_errors}건 실패했습니다. 마지막 오류: {rec.get('error')}")
            if tracker.budget is not None and tracker.spent >= tracker.budget:
                stop.set()
    except BaseException:
        # 대기 중인 문항은 취소한다. 이미 보낸 요청은 끝나는 대로 worker 가 기록한다
        stop.set()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        pool.shutdown(wait=not stop.is_set())
        if not stop.is_set():
            store.close()
        write_json(cell.run_dir / "summary.json", {"label": cell.label, "updated_at": now_iso(), **summarize(list(RunStore(cell.run_dir).load().values()))})
    plan.state = "stopped" if stop.is_set() else "done"
    c = plan.counts()
    log.info("cell 끝: %s | 정확도 %s%% (%d/%d) 오류 %d context초과 %d", cell.label, ui.fmt_pct(c["acc"]), c["correct"], c["n_done"], c["n_error"], c["n_overflow"])


def _check_paid(plans: list[CellPlan], opts: RunOptions, pricing: dict) -> bool:
    """유료 모델: 단가와 예산 상한을 확인하고, 있는 기록으로 예상 비용을 보여 준다."""
    paid = [p for p in plans if p.cell.model.paid and p.pending]
    if not paid:
        return True
    rows, total, unknown = [], 0.0, False
    for p in paid:
        price = cost.price_for(p.cell.model, pricing)
        if price is None:
            ui.error(f"{p.cell.model.key}: configs/pricing.yaml 에 단가가 없습니다. 단가를 넣은 뒤 다시 실행하세요.")
            return False
        proj = cost.project(list(p.records.values()), len(p.pending), price)
        if proj:
            total += proj["usd_remaining"]
            rows.append((p.cell.label, len(p.pending), f"{proj['avg_prompt_tokens']:.0f}", f"{proj['avg_completion_tokens']:.0f}", f"${proj['usd_remaining']:.3f}"))
        else:
            unknown = True
            rows.append((p.cell.label, len(p.pending), "?", "?", "?"))
    ui.table("유료 모델 예상 비용 (끝난 문항의 평균 token 기준)", ["cell", "남은 문항", "입력 tok", "출력 tok", "예상"], rows, right=(1, 2, 3, 4))
    if unknown:
        ui.warn("기록이 없는 cell 은 추정할 수 없습니다. `python -m ts2img estimate <실험>` 으로 5문항씩 먼저 돌려 볼 수 있습니다.")
    else:
        ui.info(f"예상 합계: ${total:.2f}")
    if opts.budget_usd is None:
        ui.error("유료 모델이 포함돼 있습니다. 지출 상한을 정해 다시 실행하세요: --budget-usd 5")
        return False
    ui.info(f"지출 상한 ${opts.budget_usd:.2f}. 상한에 닿으면 멈춥니다 (진행 중이던 요청만큼 조금 넘을 수 있음).")
    return True


def run_experiment(exp: Experiment, opts: RunOptions | None = None) -> int:
    opts = opts or RunOptions()
    exp_dir = experiment_dir(exp.name)
    prev = read_json(exp_dir / "status.json")
    if prev and prev.get("state") == "running" and prev.get("pid") != os.getpid() and not opts.force:
        if run_process_alive(prev.get("pid")):
            ui.error(f"같은 실험이 이미 실행 중입니다 (pid {prev['pid']}). `python -m ts2img status {exp.name}` 로 확인하거나 `stop` 후 다시 실행하세요.")
            return 2

    plans = make_plans(exp, retry_overflow=opts.retry_overflow)
    show_plan(exp, plans)
    if opts.dry_run:
        return 0
    if not any(p.pending for p in plans):
        ui.ok("남은 문항이 없습니다. 보고서: python -m ts2img report " + exp.name)
        return 0
    pricing = load_pricing()
    if not _check_paid(plans, opts, pricing):
        return 2

    _setup_logging(exp_dir)
    if exp.source:
        (exp_dir / "experiment.yaml").write_text(Path(exp.source).read_text(encoding="utf-8"), encoding="utf-8")
    env = sysinfo.collect(full=True)
    log.info("실험 시작: %s | %s | %s", exp.name, sysinfo.accelerator_summary(env), env["os"])
    budget = opts.budget_usd if any(p.cell.model.paid for p in plans) else None
    tracker = Tracker(exp, plans, budget)
    stop = threading.Event()
    pusher = None
    if opts.sync_dir:
        from ts2img.sync import PeriodicPush

        pusher = PeriodicPush(Path(opts.sync_dir)).start()
        ui.info(f"결과를 2분마다 복사합니다: {opts.sync_dir}")

    by_model: dict[str, list[CellPlan]] = {}
    for p in plans:
        if p.pending:
            by_model.setdefault(p.cell.model.key, []).append(p)

    state = "finished"
    try:
        for key, group in by_model.items():
            model = group[0].cell.model
            served = False
            try:
                if opts.auto_serve and model.serve:
                    from ts2img.models import serve

                    serve.start(model)
                    served = True
                client = ChatClient(model, timeout=exp.request_timeout)
                endpoint_models = client.ping()
                if endpoint_models and model.model not in endpoint_models and model.provider == "openai":
                    ui.warn(f"{key}: endpoint 의 model 목록에 '{model.model}' 이 없습니다: {endpoint_models[:5]}")
                default_sampling = _server_default_sampling(group[0].cell) if exp.sampling == "official" else None
                price = cost.price_for(model, pricing) if model.paid else None
                for plan in group:
                    if stop.is_set():
                        break
                    _write_run_meta(plan, env, endpoint_models, default_sampling)
                    _run_cell(plan, client, tracker, opts, stop, price)
            except FatalModelError as e:
                ui.error(str(e))
                log.error("모델 중단 %s: %s", key, e)
                for plan in group:
                    if plan.state in ("pending", "running"):
                        plan.state, plan.error = "failed", str(e)
                state = "failed"
                stop.clear()
            finally:
                if served:
                    from ts2img.models import serve

                    serve.stop()
            if stop.is_set():
                state = "budget_reached"
                break
    except KeyboardInterrupt:
        state = "interrupted"
        log.warning("사용자 중단")
        ui.warn("중단 요청을 받았습니다. 이미 보낸 요청의 응답만 기록하고 끝냅니다 (바로 끝내려면 한 번 더 Ctrl+C).")
    finally:
        tracker.finish(state)
        if pusher:
            pusher.stop()
        log.info("실험 끝: %s (%s)", exp.name, state)
        for h in list(log.handlers):   # run.log 를 닫는다 (노트북에서 여러 번 실행할 때 파일이 잠기지 않게)
            h.close()
            log.removeHandler(h)

    show_summary(exp, plans, tracker, state)
    return {"finished": 0, "failed": 1, "budget_reached": 3, "interrupted": 130}[state]


def show_summary(exp: Experiment, plans: list[CellPlan], tracker: Tracker | None = None, state: str = "finished") -> None:
    rows = []
    for p in plans:
        c = p.counts()
        note = p.error or ""
        rows.append((*cell_columns(p.cell), f"{c['done']}/{c['total']}", ui.fmt_pct(c["acc"]), ui.fmt_pct(c["acc_official"]),
                     c["no_answer"], c["n_error"], c["n_overflow"], "done" if c["done"] >= c["total"] else p.state, note[:60]))
    ui.table(f"결과 요약: {exp.name}",
             ["task", "model", "입력", "chart", "완료", "정확도%", "공식 방식%", "답 없음", "오류", "context 초과", "상태", "비고"],
             rows, right=(4, 5, 6, 7, 8, 9))
    msg = {
        "finished": "[green]완료[/]", "failed": "[red]일부 실패[/]. 원인을 고친 뒤 같은 명령을 다시 실행하면 남은 문항만 이어서 돕니다.",
        "budget_reached": "[yellow]지출 상한에 닿아 멈췄습니다.[/] 상한을 올려 다시 실행하면 이어서 돕니다.",
        "interrupted": "[yellow]중단됨.[/] 같은 명령을 다시 실행하면 이어서 돕니다.",
    }[state]
    if tracker:
        msg += f"\n요청 {tracker.done}건, 소요 {ui.fmt_duration(time.time() - tracker.t0)}"
        if tracker.budget is not None:
            msg += f", 지출 약 ${tracker.spent:.3f}"
    msg += f"\n보고서: python -m ts2img report {exp.name}\n상태/로그: {experiment_dir(exp.name)}"
    ui.panel(msg, title="실행 결과")
