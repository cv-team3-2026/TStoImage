"""명령줄 진입점: python -m ts2img <명령>"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ts2img import __version__, ui
from ts2img.paths import EXPERIMENTS, ROOT, experiment_dir, find_experiment, results_dir


# ---- 공통 ------------------------------------------------------------------
def _add_overrides(p: argparse.ArgumentParser) -> None:
    """yaml 값을 명령줄에서 잠깐 바꾸는 옵션. report 에도 같은 값을 줘야 같은 문항으로 집계된다."""
    p.add_argument("--models", help="모델을 바꿔 실행 (쉼표로 구분)")
    p.add_argument("--benchmarks", help="대상 task 를 바꿔 실행 (쉼표로 구분). 예: tsrbench/perception/anomaly_detection")
    p.add_argument("--modalities", help="입력 조건을 바꿔 실행 (쉼표로 구분): text,vision,text+vision")
    p.add_argument("--limit", type=int, help="unit 마다 앞에서 N 문항만")
    p.add_argument("--repeats", type=int)
    p.add_argument("--concurrency", type=int)


def _load_exp(args):
    from ts2img.config import load_experiment

    exp = load_experiment(find_experiment(args.experiment))
    for name in ("models", "benchmarks", "modalities"):
        v = getattr(args, name, None)
        if v:
            setattr(exp, name, [x.strip() for x in v.split(",") if x.strip()])
    for name in ("limit", "repeats", "concurrency"):
        v = getattr(args, name, None)
        if v is not None:
            setattr(exp, name, v)
    return exp


def _pid_alive(pid) -> bool:
    from ts2img.runner import run_process_alive

    return run_process_alive(pid)


# ---- 명령 ------------------------------------------------------------------
def cmd_sysinfo(args) -> int:
    from ts2img import sysinfo

    ui.banner(f"v{__version__}")
    sysinfo.show()
    return 0


def cmd_doctor(args) -> int:
    from ts2img import secrets, sysinfo
    from ts2img.benchmarks import benchmark_names, get_benchmark
    from ts2img.config import load_models
    from ts2img.models import serve

    ui.banner("환경 점검")
    problems = 0

    # secrets
    rows = []
    if secrets.SECRETS_FILE.is_file():
        ignored = secrets.git_ignored(secrets.SECRETS_FILE)
        rows.append(("secrets.env", "있음" + ("" if ignored else " - [red]git 이 무시하지 않습니다! .gitignore 를 확인하세요[/]")))
        problems += 0 if ignored or ignored is None else 1
    else:
        rows.append(("secrets.env", "없음 (API key 가 필요하면 secrets.example.env 를 복사해 만드세요)"))
    hits = secrets.scan_tracked_files()
    rows.append(("git 에 올라갈 파일의 key 검사", "이상 없음" if not hits else f"[red]key 처럼 보이는 문자열 발견: {', '.join(hits)}[/]"))
    problems += len(hits)
    ui.kv_table("secrets", rows)

    # 버전을 고정한 패키지: 다르면 chart 그림이나 요청 형식이 달라질 수 있다
    from importlib import metadata

    rows = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if "==" not in line or line.lstrip().startswith("#"):
            continue
        name, want = (x.strip() for x in line.split("#")[0].split("==", 1))
        try:
            have = metadata.version(name)
        except metadata.PackageNotFoundError:
            have = None
        if have != want:
            problems += 1
        rows.append((name, want, have or "없음", "OK" if have == want else "[red]다름: pip install -r requirements.txt[/]"))
    ui.table("고정 버전 패키지", ["패키지", "requirements.txt", "설치됨", ""], rows)

    # models
    models = load_models()
    rows = []
    for key, m in models.items():
        if m.provider == "mock":
            rows.append((key, "mock", "-", "-", "사용 가능"))
            continue
        kind = "직접 서빙" if m.serve else ("유료 API" if m.paid else "외부 endpoint")
        key_state = "-" if not m.api_key_env else f"{m.api_key_env}: {secrets.mask(secrets.get(m.api_key_env))}"
        url = m.resolved_base_url() or "(없음)"
        if m.base_url_env:
            url = f"({m.base_url_env}: {'설정됨' if secrets.get(m.base_url_env) else '없음'})"
        state = ""
        if args.ping:
            from ts2img.models.client import ChatClient, FatalModelError

            try:
                ids = ChatClient(m, timeout=15).ping()
                state = "[green]연결됨[/]" + (f" ({len(ids)} models)" if ids else "")
            except FatalModelError as e:
                state = f"[red]{str(e)[:70]}[/]"
        rows.append((key, kind, url, key_state, state))
    ui.table("models.yaml", ["key", "종류", "URL", "API key", "연결 (--ping)"], rows)

    # data
    rows = []
    for name in benchmark_names():
        b = get_benchmark(name)
        have = [u for u in b.units() if b.has_data(u)]
        rows.append((name, f"{len(have)} / {len(b.units())} 파일", str(b.root())))
    ui.table("데이터 (없으면 실행할 때 자동으로 받습니다)", ["benchmark", "준비됨", "위치"], rows)

    info = sysinfo.collect()
    ui.kv_table("서빙", [
        ("가속기", sysinfo.accelerator_summary(info)),
        ("vLLM venv", str(serve.venv_dir()) + (" (설치됨)" if serve.venv_python().is_file() else " (없음: serve setup 으로 설치)")),
        ("떠 있는 서버", (serve.current() or {}).get("key", "없음")),
    ])
    if problems:
        ui.error(f"확인이 필요한 항목 {problems}건")
        return 1
    ui.ok("점검 완료")
    return 0


def cmd_list(args) -> int:
    from ts2img import charts
    from ts2img.benchmarks import benchmark_names, get_benchmark
    from ts2img.config import load_experiment, load_models
    from ts2img.methods import method_names

    for name in benchmark_names():
        b = get_benchmark(name)
        rows = [(f"{name}/{u}", b.n_samples(u) or "") for u in b.units()]
        ui.table(f"benchmark: {name} (상위 경로로 묶어 선택 가능. 예: {name}, {name}/reasoning)", ["task", "문항"], rows, right=(1,))
        subs = [t for t in b.leaf_tasks() if t not in b.units()]
        if subs:
            ui.info("하위 task: " + ", ".join(f"{name}/{t}" for t in subs))
    rows = [(n, ", ".join(f"{k}={v}" for k, v in charts.chart_params(n).items()) or "-",
             (charts.get_chart(n).__doc__ or "").strip().splitlines()[0]) for n in charts.chart_names()]
    ui.table("charts", ["이름", "옵션 (기본값)", "설명"], rows)
    ui.info("후처리(post): " + ", ".join(charts._post.FILTERS) + " | method: " + ", ".join(method_names()))
    rows = [(k, m.model, "mock" if m.provider == "mock" else "직접 서빙" if m.serve else "유료 API" if m.paid else "외부 endpoint", m.notes)
            for k, m in load_models().items()]
    ui.table("models", ["key", "model", "종류", "메모"], rows)
    rows = []
    for p in sorted(EXPERIMENTS.glob("*.y*ml")):
        try:
            e = load_experiment(p)
            rows.append((p.stem, ", ".join(e.benchmarks), ", ".join(e.models), ", ".join(e.modalities), len(e.charts)))
        except Exception as err:
            rows.append((p.stem, f"[red]설정 오류: {err}[/]", "", "", ""))
    ui.table("experiments (configs/experiments)", ["이름", "대상", "모델", "입력", "chart 수"], rows, right=(4,))
    return 0


def cmd_download(args) -> int:
    from ts2img import benchmarks

    for name, sels in benchmarks.resolve(args.selectors or ["tsrbench"]).items():
        benchmarks.get_benchmark(name).ensure_data([s.unit for s in sels])
        ui.ok(f"{name}: 준비 완료 ({len(sels)} 파일)")
    return 0


def cmd_preview(args) -> int:
    from ts2img import preview
    from ts2img.config import load_experiment

    exp = load_experiment(find_experiment(args.exp)) if args.exp else None
    if args.what == "charts":
        specs = preview.parse_charts(args.charts, exp)
        if args.examples:
            samples = preview.example_samples()
        else:
            samples = preview.task_samples(args.task or (exp.benchmarks[0] if exp else "tsrbench/perception"))
            samples = [samples[p] for p in args.pos] if args.pos else samples[: args.n]
        path = preview.chart_gallery(specs, samples, Path(args.out) if args.out else None)
        ui.ok(f"chart 미리보기 저장: {path} (chart {len(specs)}개 x 문항 {len(samples)}개)")
    else:
        chart = preview.parse_charts(args.charts, exp)[0] if (args.charts or exp) else None
        info = preview.prompt_preview(
            args.task or (exp.benchmarks[0] if exp else "tsrbench/perception"), args.modality, chart,
            args.pos[0] if args.pos else 0, find_experiment(args.exp) if args.exp else None, args.model,
        )
        preview.print_prompt(info, args.max_chars)
    return 0


def cmd_serve(args) -> int:
    from ts2img.config import load_models
    from ts2img.models import serve

    if args.action == "status":
        serve.show_status()
        return 0
    if args.action == "stop":
        if not serve.stop():
            ui.info("떠 있는 서버가 없습니다.")
        return 0
    if args.action == "setup":
        serve.setup(force=args.force)
        return 0
    models = load_models()
    if not args.model:
        ui.error("모델을 지정하세요. 직접 띄울 수 있는 모델: " + ", ".join(k for k, m in models.items() if m.serve))
        return 2
    if args.model not in models:
        ui.error(f"models.yaml 에 없는 모델: {args.model}")
        return 2
    spec = models[args.model]
    if args.dry_run:
        cmd, env = serve.build_command(spec)
        ui.panel(" ".join(cmd) + "\n\n" + "\n".join(f"{k}={v}" for k, v in env.items()), title="실행될 명령 (dry-run)")
        return 0
    serve.start(spec, wait=not args.no_wait)
    return 0


def _spawn_background(argv: list[str], name: str) -> int:
    """노트북이나 SSH 연결과 분리된 프로세스로 다시 실행한다."""
    exp_dir = experiment_dir(name)
    exp_dir.mkdir(parents=True, exist_ok=True)
    out_path = exp_dir / "stdout.log"
    out = open(out_path, "a", encoding="utf-8")
    cmd = [sys.executable, "-m", "ts2img", *[a for a in argv if a != "--background"]]
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    for k in ("COLAB_RELEASE_TAG", "JPY_PARENT_PID"):  # 로그 파일에는 색 코드를 넣지 않는다
        env.pop(k, None)
    kwargs: dict = dict(stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=ROOT, env=env)
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)
    ui.panel(
        "백그라운드에서 실행을 시작했습니다. 이 창(셀)을 닫아도 계속 돕니다.\n"
        f"진행 확인: python -m ts2img status {name}\n"
        f"중지:      python -m ts2img stop {name}\n"
        f"출력:      {out_path}",
        title="백그라운드 실행",
    )
    return 0


def cmd_run(args) -> int:
    from ts2img.runner import RunOptions, _check_paid, make_plans, run_experiment, show_plan
    from ts2img.config import load_pricing

    exp = _load_exp(args)
    sync_dir = args.sync_dir or os.environ.get("TS2IMG_SYNC_DIR")
    opts = RunOptions(budget_usd=args.budget_usd, auto_serve=args.auto_serve, dry_run=args.dry_run,
                      sync_dir=Path(sync_dir) if sync_dir else None, force=args.force, retry_overflow=args.retry_overflow)
    if args.background and not args.dry_run:
        ui.banner(f"실험: {exp.name}")
        plans = make_plans(exp, retry_overflow=opts.retry_overflow)
        show_plan(exp, plans)
        if not any(p.pending for p in plans):
            ui.ok("남은 문항이 없습니다.")
            return 0
        if not _check_paid(plans, opts, load_pricing()):
            return 2
        return _spawn_background(sys.argv[1:] if args._argv is None else args._argv, exp.name)
    # stop 명령(SIGINT/SIGTERM)을 받으면 상태를 기록하고 끝나게 한다
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, signal.default_int_handler)
        except (ValueError, OSError):
            pass
    ui.banner(f"실험: {exp.name}")
    return run_experiment(exp, opts)


def cmd_estimate(args) -> int:
    from ts2img import cost
    from ts2img.config import load_pricing
    from ts2img.runner import RunOptions, make_plans, run_experiment

    exp = _load_exp(args)
    pricing = load_pricing()
    full_limit = exp.limit
    plans = make_plans(exp)
    paid = [p for p in plans if p.cell.model.paid]
    if not paid:
        ui.info("유료 모델이 없습니다. 비용이 들지 않습니다.")
        return 0
    need_pilot = [p for p in paid if sum(1 for r in p.records.values() if r.get("status") == "ok") < args.pilot and p.pending]
    if need_pilot:
        ui.info(f"token 사용량을 재기 위해 cell 마다 {args.pilot}문항을 실제로 보냅니다 (상한 ${args.budget_usd}). 결과는 본실험에 그대로 쓰입니다.")
        exp.limit = args.pilot
        exp.models = sorted({p.cell.model.key for p in paid})
        code = run_experiment(exp, RunOptions(budget_usd=args.budget_usd))
        if code not in (0, 3):
            return code
        exp = _load_exp(args)
        exp.limit = full_limit
        plans = [p for p in make_plans(exp) if p.cell.model.paid]
    else:
        plans = paid
    rows, total = [], 0.0
    for p in plans:
        proj = cost.project(list(p.records.values()), len(p.pending), cost.price_for(p.cell.model, pricing))
        if proj:
            total += proj["usd_remaining"]
            rows.append((p.cell.label, len(p.pending), f"{proj['avg_prompt_tokens']:.0f}", f"{proj['avg_completion_tokens']:.0f}",
                         f"${proj['usd_per_sample']:.5f}", f"${proj['usd_remaining']:.3f}"))
        else:
            rows.append((p.cell.label, len(p.pending), "?", "?", "?", "?"))
    ui.table("예상 비용", ["cell", "남은 문항", "입력 tok", "출력 tok", "문항당", "합계"], rows, right=(1, 2, 3, 4, 5))
    ui.panel(f"남은 문항 전체 예상: ${total:.2f}\n실행: python -m ts2img run {args.experiment} --budget-usd {max(1, round(total * 1.3 + 0.5))}", title="비용 추정")
    return 0


def _show_status(name: str) -> str:
    from ts2img.store import read_json

    st = read_json(experiment_dir(name) / "status.json")
    if not st:
        ui.info(f"{name}: 실행 기록이 없습니다.")
        return "none"
    state = st["state"]
    if state == "running" and not _pid_alive(st.get("pid")):
        state = "dead"
    label = {
        "running": "[green]실행 중[/]", "finished": "[green]완료[/]", "failed": "[red]일부 실패[/]",
        "interrupted": "[yellow]중단됨[/]", "budget_reached": "[yellow]지출 상한 도달[/]",
        "dead": "[red]프로세스가 종료됨[/] (같은 명령을 다시 실행하면 이어서 돕니다)",
    }.get(state, state)
    done, total = st["requests_done"], st["requests_total"]
    frac = done / total if total else 1.0
    lines = [
        f"상태: {label}  (pid {st.get('pid')})",
        f"진행: {ui.bar(frac)} {done} / {total} ({100 * frac:.1f}%)",
        f"경과: {ui.fmt_duration(st.get('elapsed_s'))}" + (f" | 남은 시간: ~{ui.fmt_duration(st.get('eta_s'))}" if state == "running" else ""),
        f"시작: {st.get('started_at')} | 갱신: {st.get('updated_at')}",
    ]
    if st.get("budget_usd") is not None:
        lines.append(f"지출: ${st.get('spent_usd')} / ${st.get('budget_usd')}")
    if st.get("current") and state == "running":
        lines.append(f"현재: {st['current']}")
    ui.panel("\n".join(lines), title=f"실험: {name}")
    if not getattr(_show_status, "compact", False):
        rows = [(*(c.get("columns") or [c["label"], "", "", ""]), f"{c['done']}/{c['total']}", ui.fmt_pct(c.get("acc")), c.get("n_error"), c.get("n_overflow"), c["state"], (c.get("error") or "")[:50])
                for c in st.get("cells", [])]
        ui.table("", ["task", "model", "입력", "chart", "완료", "정확도%", "오류", "context 초과", "상태", "비고"], rows, right=(4, 5, 6, 7))
    return state


def cmd_status(args) -> int:
    names = [args.name] if args.name else sorted(p.name for p in (results_dir() / "experiments").glob("*") if (p / "status.json").is_file())
    if not names:
        ui.info("실행 기록이 없습니다.")
        return 0
    if args.watch and len(names) == 1:
        _show_status(names[0])
        _show_status.compact = True
        try:
            while True:
                time.sleep(args.interval)
                if _show_status(names[0]) != "running":
                    break
        except KeyboardInterrupt:
            pass
        finally:
            _show_status.compact = False
        return 0
    for n in names:
        _show_status(n)
    return 0


def cmd_stop(args) -> int:
    import psutil

    from ts2img.store import now_iso, read_json, write_json

    path = experiment_dir(args.name) / "status.json"
    st = read_json(path)
    if not st or st.get("state") != "running" or not _pid_alive(st.get("pid")):
        ui.info(f"{args.name}: 실행 중이 아닙니다.")
        return 0
    pid = st["pid"]
    proc = psutil.Process(pid)
    if os.name == "nt":
        proc.terminate()   # Windows 에는 SIGINT 를 보낼 방법이 없어 바로 끝낸다. 기록된 문항은 남는다
    else:
        os.kill(pid, signal.SIGINT)  # 정리(상태 기록, 서버 종료)를 마치고 끝나게 한다
    try:
        proc.wait(timeout=30)
    except psutil.TimeoutExpired:
        for c in proc.children(recursive=True):
            c.kill()
        proc.kill()
    st = read_json(path) or st
    if st.get("state") == "running":
        st.update(state="interrupted", updated_at=now_iso())
        write_json(path, st)
    ui.ok(f"{args.name}: 중지했습니다 (pid {pid}). 같은 run 명령을 다시 실행하면 이어서 돕니다.")
    return 0


def cmd_report(args) -> int:
    from ts2img.report.build import build_report

    exp = _load_exp(args)
    out = build_report(exp, Path(args.out) if args.out else None)
    ui.info(f"파일: {out / 'report.md'}, {out / 'report.html'}, {out / 'summary.csv'}")
    return 0


def cmd_sync(args) -> int:
    from ts2img import sync

    target = args.dir or os.environ.get("TS2IMG_SYNC_DIR")
    if not target:
        ui.error("--dir 또는 환경변수 TS2IMG_SYNC_DIR 로 위치를 지정하세요.")
        return 2
    n = sync.push(Path(target)) if args.action == "push" else sync.restore(Path(target))
    ui.ok(f"{args.action}: 파일 {n}개 ({target})")
    return 0


# ---- parser ----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m ts2img", description="time series chart 실험 도구")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("sysinfo", help="현재 컴퓨터 사양 출력").set_defaults(fn=cmd_sysinfo)

    s = sub.add_parser("doctor", help="secrets, 모델 연결, 데이터 점검")
    s.add_argument("--ping", action="store_true", help="각 모델 endpoint 에 실제로 연결해 본다")
    s.set_defaults(fn=cmd_doctor)

    sub.add_parser("list", help="benchmark / chart / model / 실험 목록").set_defaults(fn=cmd_list)

    s = sub.add_parser("download", help="벤치마크 데이터 받기 (있으면 건너뜀)")
    s.add_argument("selectors", nargs="*", help="예: tsrbench, tsrbench/perception")
    s.set_defaults(fn=cmd_download)

    s = sub.add_parser("preview", help="모델 호출 없이 chart / prompt 미리보기")
    s.add_argument("what", choices=["charts", "prompt"])
    s.add_argument("--exp", help="실험 yaml 의 charts 와 설정을 쓴다")
    s.add_argument("--task", help="예: tsrbench/perception/anomaly_detection")
    s.add_argument("--charts", nargs="*", help='예: tsrbench_baseline "{use: line_style, linewidth: 4}"')
    s.add_argument("--modality", default="vision", choices=["text", "vision", "text+vision"])
    s.add_argument("--model")
    s.add_argument("--n", type=int, default=3, help="문항 수 (charts)")
    s.add_argument("--pos", type=int, nargs="*", help="선택된 문항 중 몇 번째인지 (0부터)")
    s.add_argument("--examples", action="store_true", help="augmentation_examples/ 의 9개로 그린다")
    s.add_argument("--out", help="저장 경로 (charts)")
    s.add_argument("--max-chars", type=int, default=6000)
    s.set_defaults(fn=cmd_preview)

    s = sub.add_parser("serve", help="로컬 VLM 서버 (vLLM)")
    s.add_argument("action", choices=["setup", "start", "stop", "status"])
    s.add_argument("model", nargs="?")
    s.add_argument("--dry-run", action="store_true", help="실행될 명령만 보여 준다")
    s.add_argument("--no-wait", action="store_true", help="준비될 때까지 기다리지 않는다")
    s.add_argument("--force", action="store_true", help="setup: 다시 설치")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("run", help="실험 실행 (끝난 문항은 건너뛰고 이어서 실행)")
    s.add_argument("experiment", help="configs/experiments 안의 이름 또는 yaml 경로")
    _add_overrides(s)
    s.add_argument("--background", action="store_true", help="창을 닫아도 계속 돌게 분리해 실행")
    s.add_argument("--auto-serve", action="store_true", help="serve 블록이 있는 모델을 자동으로 띄우고 끝나면 끈다")
    s.add_argument("--budget-usd", type=float, help="유료 모델 지출 상한 (유료 모델이면 필수)")
    s.add_argument("--dry-run", action="store_true", help="계획만 보여 준다")
    s.add_argument("--sync-dir", help="결과를 2분마다 복사할 위치 (예: Google Drive)")
    s.add_argument("--force", action="store_true", help="같은 실험이 실행 중이라는 기록을 무시")
    s.add_argument("--retry-overflow", action="store_true", help="context 초과로 끝난 문항을 다시 보낸다")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("estimate", help="유료 모델 예상 비용 (cell 마다 몇 문항을 실제로 보내 잰다)")
    s.add_argument("experiment")
    _add_overrides(s)
    s.add_argument("--pilot", type=int, default=5)
    s.add_argument("--budget-usd", type=float, default=0.5, help="측정에 쓸 지출 상한")
    s.set_defaults(fn=cmd_estimate)

    s = sub.add_parser("status", help="진행 상황")
    s.add_argument("name", nargs="?")
    s.add_argument("--watch", action="store_true", help="끝날 때까지 주기적으로 표시")
    s.add_argument("--interval", type=float, default=10)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("stop", help="실행 중인 실험 중지")
    s.add_argument("name")
    s.set_defaults(fn=cmd_stop)

    s = sub.add_parser("report", help="보고서 생성")
    s.add_argument("experiment")
    _add_overrides(s)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("sync", help="results 폴더를 다른 위치와 맞춘다")
    s.add_argument("action", choices=["push", "restore"])
    s.add_argument("--dir")
    s.set_defaults(fn=cmd_sync)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args._argv = argv
    try:
        return args.fn(args) or 0
    except KeyboardInterrupt:
        ui.warn("중단됨")
        return 130
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as e:
        msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        ui.error(str(msg))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
