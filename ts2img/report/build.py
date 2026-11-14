"""보고서 생성: report.md, report.html(이미지 포함 단일 파일), summary.csv, figures/."""
from __future__ import annotations

import base64
import csv
import re
from collections import defaultdict
from pathlib import Path

from ts2img import charts, ui
from ts2img.benchmarks import get_benchmark
from ts2img.config import Experiment
from ts2img.paths import reports_dir
from ts2img.report import stats
from ts2img.runner import CellPlan, make_plans
from ts2img.store import now_iso, read_json


def _pct(x, digits=1):
    return "-" if x is None else f"{100 * x:.{digits}f}"


def _ci(ci):
    return "" if not ci else f"[{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]"


def _p(p):
    if p is None:
        return "-"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _md_table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v).replace("|", "\\|").replace("\n", " ") for v in r) + " |")
    return "\n".join(out)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


class _Group:
    """(benchmark, model, modality) 하나. chart label -> repeat -> {문항 id: 기록}."""

    def __init__(self, bench: str, model: str, modality: str):
        self.bench, self.model, self.modality = bench, model, modality
        self.records: dict[str, dict[int, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
        self.samples: dict[str, object] = {}
        self.plans: dict[str, list[CellPlan]] = defaultdict(list)
        self.charts: dict[str, object] = {}

    def add(self, plan: CellPlan) -> None:
        label = plan.cell.chart.label
        self.records[label][plan.cell.repeat].update(plan.records)
        self.plans[label].append(plan)
        self.charts[label] = plan.cell.chart
        for s in plan.samples:
            self.samples[s.id] = s

    @property
    def title(self) -> str:
        return f"{self.bench} / {self.model} / {self.modality}"

    def recs(self, label: str, repeat: int = 0) -> dict[str, dict]:
        return self.records[label].get(repeat, {})

    def repeats(self, label: str) -> list[int]:
        return sorted(self.records[label])


def _collect(plans: list[CellPlan]) -> dict[tuple, _Group]:
    groups: dict[tuple, _Group] = {}
    for p in plans:
        c = p.cell
        key = (c.benchmark, c.model.key, c.modality)
        groups.setdefault(key, _Group(*key)).add(p)
    return groups


# ---- 그림 ------------------------------------------------------------------
def _stitch(images):
    """여러 장이면 가로로 이어 붙인다."""
    from PIL import Image

    pils = [im.pil().convert("RGB") for im in images]
    if len(pils) == 1:
        return pils[0]
    h = max(p.height for p in pils)
    canvas = Image.new("RGB", (sum(p.width for p in pils) + 8 * (len(pils) - 1), h), "white")
    x = 0
    for p in pils:
        canvas.paste(p, (x, 0))
        x += p.width + 8
    return canvas


def _grid_figure(cells: list[list], row_labels: list[str], col_labels: list[str], path: Path) -> None:
    """이미지 격자를 한 장으로 저장한다. cells[r][c] 는 PIL 이미지 또는 None."""
    import matplotlib.pyplot as plt

    with charts.RENDER_LOCK:
        nr, nc = len(cells), len(cells[0])
        fig, axes = plt.subplots(nr, nc, figsize=(5.2 * nc, 2.6 * nr), squeeze=False)
        for r in range(nr):
            for c in range(nc):
                ax = axes[r][c]
                ax.set_xticks([])
                ax.set_yticks([])
                for sp in ax.spines.values():
                    sp.set_visible(False)
                if cells[r][c] is not None:
                    ax.imshow(cells[r][c])
                else:
                    ax.text(0.5, 0.5, "(no image)", ha="center", va="center", color="gray")
                if r == 0:
                    ax.set_title(col_labels[c], fontsize=9)
                if c == 0:
                    ax.set_ylabel(row_labels[r], fontsize=8, rotation=0, ha="right", va="center", labelpad=6)
        fig.tight_layout()
        path.parent.mkdir(parents=True, exist_ok=True)
        # chart 를 모은 그림은 JPEG 로 저장한다 (PNG 의 1/10 크기. 보고서는 git 에 올린다)
        fig.savefig(path, dpi=110, bbox_inches="tight", pil_kwargs={"quality": 88})
        plt.close(fig)


def _render(sample, chart):
    images = charts.render(sample, chart.use, chart.params, chart.post)
    return _stitch(images) if images else None


def _gallery(group: _Group, labels: list[str], fig_dir: Path, per_task: int = 1, max_cols: int = 4) -> list[tuple[str, str]]:
    """같은 문항을 chart 별로 나란히 그린 그림. unit 마다 한 장."""
    by_unit: dict[str, list] = defaultdict(list)
    seen_task: dict[str, int] = defaultdict(int)
    for s in group.samples.values():
        if seen_task[s.task] < per_task and len(by_unit[s.unit]) < max_cols:
            seen_task[s.task] += 1
            by_unit[s.unit].append(s)
    out = []
    for unit, samples in by_unit.items():
        # chart 는 model, 입력 조건과 무관하므로 unit 마다 한 장만 만들어 같이 쓴다
        name = f"gallery_{_safe(unit)}.jpg"
        if not (fig_dir / name).is_file():
            cells = [[_render(s, group.charts[lb]) for s in samples] for lb in labels]
            _grid_figure(cells, labels, [f"{s.task} #{s.idx}" for s in samples], fig_dir / name)
        out.append((unit, name))
    return out


def _accuracy_figure(group: _Group, rows: list[dict], path: Path) -> None:
    import matplotlib.pyplot as plt

    with charts.RENDER_LOCK:
        labels = [r["label"] for r in rows if r["acc"] is not None]
        accs = [100 * r["acc"] for r in rows if r["acc"] is not None]
        if not accs:
            return
        lo = [100 * (r["acc"] - r["ci"][0]) for r in rows if r["acc"] is not None]
        hi = [100 * (r["ci"][1] - r["acc"]) for r in rows if r["acc"] is not None]
        fig, ax = plt.subplots(figsize=(7, 0.5 * len(labels) + 1.2))
        y = range(len(labels))
        ax.barh(y, accs, xerr=[lo, hi], color=["#888888"] + ["#4C72B0"] * (len(labels) - 1), capsize=3)
        ax.set_yticks(list(y))
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Accuracy (%) with 95% CI")
        ax.set_title(group.title, fontsize=10)
        ax.axvline(accs[0], color="gray", linestyle=":", linewidth=1)
        ax.grid(True, axis="x", alpha=0.3)
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)


def _flip_figure(group: _Group, base_label: str, label: str, ids: list[str], path: Path) -> bool:
    samples = [group.samples[i] for i in ids[:3] if i in group.samples]
    if not samples:
        return False
    cells = [[_render(s, group.charts[base_label]) for s in samples], [_render(s, group.charts[label]) for s in samples]]
    cols = []
    for s in samples:
        b, v = group.recs(base_label)[s.id], group.recs(label)[s.id]
        cols.append(f"{s.task} #{s.idx} | answer {s.answer} | base {b.get('pred')} -> variant {v.get('pred')}")
    _grid_figure(cells, [base_label, label], cols, path)
    return True


# ---- 본문 ------------------------------------------------------------------
def _main_rows(group: _Group, labels: list[str], base_label: str) -> list[dict]:
    rows = []
    base = group.recs(base_label)
    n_selected = len(group.samples)
    for lb in labels:
        recs = group.recs(lb)
        s = stats.summarize(list(recs.values()))
        row = {"label": lb, "is_base": lb == base_label, "n_selected": n_selected, **s, "paired": None}
        if lb != base_label and base and recs:
            row["paired"] = stats.paired(base, recs)
        reps = group.repeats(lb)
        if len(reps) > 1:
            accs = [stats.summarize(list(group.recs(lb, r).values()))["acc"] for r in reps]
            accs = [a for a in accs if a is not None]
            row["repeat_accs"] = accs
        rows.append(row)
    # Holm 보정: 같은 표 안의 비교 전체
    idx = [i for i, r in enumerate(rows) if r["paired"] and r["paired"]["p"] is not None]
    for i, adj in zip(idx, stats.holm([rows[i]["paired"]["p"] for i in idx])):
        rows[i]["paired"]["p_holm"] = adj
    return rows


def _task_table(group: _Group, labels: list[str], base_label: str) -> str:
    tasks = sorted({s.task for s in group.samples.values()})
    if len(tasks) <= 1:
        return ""
    header = ["task", "문항"] + labels
    rows = []
    for t in tasks:
        ids = [i for i, s in group.samples.items() if s.task == t]
        base_acc = None
        row = [t, len(ids)]
        for lb in labels:
            recs = group.recs(lb)
            s = stats.summarize([recs[i] for i in ids if i in recs])
            if lb == base_label:
                base_acc = s["acc"]
            if s["acc"] is None:
                row.append("-")
            elif lb == base_label or base_acc is None:
                row.append(_pct(s["acc"]))
            else:
                row.append(f"{_pct(s['acc'])} ({100 * (s['acc'] - base_acc):+.1f})")
        rows.append(row)
    return _md_table(header, rows)


def build_report(exp: Experiment, out_dir: Path | None = None) -> Path:
    plans = make_plans(exp)
    out = out_dir or reports_dir() / exp.name
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for old in fig_dir.iterdir():   # 이전 보고서의 그림을 지운다
        if old.is_file():
            old.unlink()
    groups = _collect(plans)
    base_label = exp.baseline_label()
    chart_labels = [c.label for c in exp.charts]
    if base_label not in chart_labels:
        raise ValueError(f"baseline '{base_label}' 이 charts 에 없습니다: {chart_labels}")
    ordered = [base_label] + [lb for lb in chart_labels if lb != base_label]

    total = sum(len(p.samples) for p in plans)
    done = sum(len(p.samples) - len(p.pending) for p in plans)
    md: list[str] = [f"# 실험 보고서: {exp.name}", ""]
    if exp.description:
        md += [exp.description.strip(), ""]
    md += [
        f"- 생성: {now_iso()}",
        f"- 진행: {done} / {total} 요청 완료 ({100 * done / max(1, total):.1f}%)" + ("" if done == total else " - **미완료 상태의 중간 결과**"),
        f"- 대상: {', '.join(exp.benchmarks)} | 모델: {', '.join(exp.models)} | 입력: {', '.join(exp.modalities)}",
        f"- sampling: `{exp.sampling if isinstance(exp.sampling, str) else exp.sampling_params()}`, repeats {exp.repeats}, "
        f"max_tokens {exp.max_tokens if exp.max_tokens else '없음(공식)'}, text 값 간격 {exp.text_stride}" + (f", limit {exp.limit}" if exp.limit else ""),
        f"- 비교 기준(baseline): `{base_label}`",
        "",
        "읽는 법",
        "",
        "- 정확도: 처리가 끝난 문항 중 정답 비율. 답 글자를 못 뽑은 응답과 context 초과 문항은 오답으로 친다. 대괄호는 95% 신뢰구간.",
        "- 공식 방식: TSRBench 공식 채점처럼 JSON 으로 읽히지 않은 응답을 분모에서 뺀 값.",
        "- 차이: 같은 문항끼리 baseline 과 비교한 값(%p). 얻음/잃음 = baseline 에서 틀렸다가 맞은 / 맞았다가 틀린 문항 수.",
        "- p: McNemar exact test. p(Holm) 은 같은 표 안의 여러 비교를 보정한 값이다.",
        "",
    ]

    csv_rows: list[dict] = []
    galleries: dict[str, str] = {}   # unit -> 그림 파일. chart 는 model, 입력 조건과 무관해 한 번만 싣는다
    vision_groups = [g for g in groups.values() if g.modality != "text"]
    text_groups = {(g.bench, g.model): g for g in groups.values() if g.modality == "text"}

    for g in vision_groups:
        labels = [lb for lb in ordered if lb in g.records]
        if not labels:
            continue
        rows = _main_rows(g, labels, base_label)
        md += [f"## {g.title}", ""]
        table = []
        for r in rows:
            pr = r["paired"]
            name = f"**{r['label']}** (baseline)" if r["is_base"] else r["label"]
            table.append([
                name, r["n_done"], f"{_pct(r['acc'])} {_ci(r['ci'])}",
                "" if not pr or pr["diff"] is None else f"{100 * pr['diff']:+.1f} {_ci(pr['diff_ci'])}",
                "" if not pr else f"{pr['gained']} / {pr['lost']}",
                "" if not pr else _p(pr["p"]),
                "" if not pr else _p(pr.get("p_holm")),
                _pct(r["acc_official"]),
                r["no_answer"],
                f"{100 * r['n_done'] / max(1, r['n_selected']):.0f}%",
            ])
        md += [_md_table(["chart", "문항 수", "정확도 % [95% CI]", "차이 %p [95% CI]", "얻음 / 잃음", "p", "p (Holm)", "공식 방식 %", "답 없음", "처리율"], table), ""]

        # 기준선
        answers = [s.answer for s in g.samples.values()]
        maj = stats.majority_baseline(answers)
        refs = []
        if maj:
            refs.append(f"최빈 정답({maj[0]})만 찍으면 {_pct(maj[1])}%")
        tg = text_groups.get((g.bench, g.model))
        if tg:
            ts = stats.summarize(list(tg.recs("none").values()))
            if ts["n_done"]:
                refs.append(f"text 만 입력(chart 없음) {_pct(ts['acc'])}% {_ci(ts['ci'])}, {ts['n_done']}문항")
        if refs:
            md += ["기준선: " + " / ".join(refs), ""]

        name = f"accuracy_{_safe(g.model)}_{_safe(g.modality)}.png"
        _accuracy_figure(g, rows, fig_dir / name)
        if (fig_dir / name).is_file():
            md += [f"![accuracy](figures/{name})", ""]

        tt = _task_table(g, labels, base_label)
        if tt:
            md += ["### task 별 정확도 % (괄호: baseline 대비 %p)", "", tt, ""]

        if any("repeat_accs" in r for r in rows):
            md += ["### 실행 간 변동 (같은 설정 반복)", ""]
            rep = []
            for r in rows:
                accs = r.get("repeat_accs")
                if accs and len(accs) > 1:
                    noise = stats.paired(g.recs(r["label"], 0), g.recs(r["label"], 1))
                    flip = (noise["gained"] + noise["lost"]) / noise["n"] if noise["n"] else None
                    rep.append([r["label"], ", ".join(_pct(a) for a in accs), _pct(sum(accs) / len(accs)),
                                f"{100 * (max(accs) - min(accs)):.1f}", _pct(flip)])
            md += [_md_table(["chart", "반복별 정확도 %", "평균 %", "범위 %p", "r0-r1 사이 정오가 바뀐 문항 %"], rep), "",
                   "chart 간 차이가 이 범위보다 작으면 실행 간 변동과 구분되지 않는다. 위 표의 차이와 p 는 첫 번째 실행(r0) 기준이다.", ""]

        # 뒤집힌 문항
        flips = [r for r in rows if r["paired"] and (r["paired"]["gained"] or r["paired"]["lost"])]
        if flips:
            md += ["### baseline 과 정오가 바뀐 문항", ""]
            for r in flips:
                pr = r["paired"]
                md += [f"- `{r['label']}`: 얻음 {pr['gained']} (예: {', '.join(pr['gained_ids'][:5]) or '-'}) / 잃음 {pr['lost']} (예: {', '.join(pr['lost_ids'][:5]) or '-'})"]
            md.append("")
            top = max(flips, key=lambda r: abs(r["paired"]["diff"] or 0))
            for kind, ids, word in (("gained", top["paired"]["gained_ids"], "틀림 -> 맞음"), ("lost", top["paired"]["lost_ids"], "맞음 -> 틀림")):
                name = f"flips_{kind}_{_safe(g.model)}_{_safe(g.modality)}.jpg"
                if _flip_figure(g, base_label, top["label"], ids, fig_dir / name):
                    md += [f"`{top['label']}` 에서 {word} 인 문항 (위: baseline, 아래: 변형)", "", f"![flips](figures/{name})", ""]

        # 부가 정보
        extra = []
        for r in rows:
            size = "x".join(str(v) for v in r["image_size"]) if r["image_size"] else "-"
            extra.append([
                r["label"], "-" if r["prompt_tokens"] is None else f"{r['prompt_tokens']:.0f}",
                "-" if r["completion_tokens"] is None else f"{r['completion_tokens']:.0f}",
                "-" if r["latency_median"] is None else f"{r['latency_median']:.1f}",
                "-" if r["images_per_sample"] is None else f"{r['images_per_sample']:.1f}", size,
                "-" if r["image_bytes"] is None else f"{r['image_bytes'] / 1024:.0f}",
                r["retried"], r["truncated"], r["n_error"], r["n_overflow"],
            ])
        md += ["### 비용과 입력 크기", "",
               _md_table(["chart", "입력 tok", "출력 tok", "응답 시간 s (중앙값)", "이미지 수", "이미지 px (최빈)", "이미지 KB", "재요청", "길이 한도로 잘림", "오류", "context 초과"], extra), ""]

        for unit, name in _gallery(g, labels, fig_dir, per_task=1):
            galleries.setdefault(unit, name)

        for lb in labels:
            for rep in g.repeats(lb):
                recs = g.recs(lb, rep)
                plans_lb = [p for p in g.plans[lb] if p.cell.repeat == rep]
                for task in ["ALL"] + sorted({s.task for s in g.samples.values()}):
                    sub = [r for i, r in recs.items() if task == "ALL" or g.samples[i].task == task]
                    s = stats.summarize(sub)
                    csv_rows.append({
                        "benchmark": g.bench, "model": g.model, "modality": g.modality, "chart": lb, "repeat": rep, "task": task,
                        "n_done": s["n_done"], "correct": s["correct"], "acc": s["acc"],
                        "ci_lo": s["ci"][0] if s["ci"] else None, "ci_hi": s["ci"][1] if s["ci"] else None,
                        "acc_official": s["acc_official"], "no_answer": s["no_answer"], "non_json": s["non_json"],
                        "n_error": s["n_error"], "n_overflow": s["n_overflow"],
                        "hash": " ".join(p.cell.hash for p in plans_lb),
                    })

    for (bench, model), tg in text_groups.items():
        recs = tg.recs("none")
        s = stats.summarize(list(recs.values()))
        md += [f"## {bench} / {model} / text (chart 없음)", "",
               _md_table(["문항 수", "정확도 % [95% CI]", "공식 방식 %", "답 없음", "context 초과", "처리율"],
                         [[s["n_done"], f"{_pct(s['acc'])} {_ci(s['ci'])}", _pct(s["acc_official"]), s["no_answer"], s["n_overflow"],
                           f"{100 * s['n_done'] / max(1, len(tg.samples)):.0f}%"]]), ""]
        tasks = sorted({x.task for x in tg.samples.values()})
        if len(tasks) > 1:
            rows = []
            for t in tasks:
                ids = [i for i, x in tg.samples.items() if x.task == t]
                st = stats.summarize([recs[i] for i in ids if i in recs])
                rows.append([t, len(ids), st["n_done"], _pct(st["acc"]), st["n_overflow"]])
            md += [_md_table(["task", "문항", "처리됨", "정확도 %", "context 초과"], rows), ""]
        for rep in tg.repeats("none"):
            for task in ["ALL"] + tasks:
                sub = [r for i, r in tg.recs("none", rep).items() if task == "ALL" or tg.samples[i].task == task]
                st = stats.summarize(sub)
                csv_rows.append({
                    "benchmark": bench, "model": model, "modality": "text", "chart": "none", "repeat": rep, "task": task,
                    "n_done": st["n_done"], "correct": st["correct"], "acc": st["acc"],
                    "ci_lo": st["ci"][0] if st["ci"] else None, "ci_hi": st["ci"][1] if st["ci"] else None,
                    "acc_official": st["acc_official"], "no_answer": st["no_answer"], "non_json": st["non_json"],
                    "n_error": st["n_error"], "n_overflow": st["n_overflow"],
                    "hash": " ".join(p.cell.hash for p in tg.plans["none"] if p.cell.repeat == rep),
                })

    if galleries:
        md += ["## chart 예시", "", "같은 문항을 chart 별로 그린 것 (행 = chart, 열 = 문항).", ""]
        for unit, name in galleries.items():
            md += [f"### {unit}", "", f"![gallery](figures/{name})", ""]

    md += _env_section(plans)

    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    if csv_rows:
        with open(out / "summary.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
            w.writeheader()
            w.writerows(csv_rows)
    _write_html(out, "\n".join(md), exp.name)
    ui.ok(f"보고서: {out / 'report.md'}")
    return out


def _env_section(plans: list[CellPlan]) -> list[str]:
    md = ["## 실행 환경과 설정", ""]
    seen_models = set()
    env = None
    rows = []
    for p in plans:
        cfg = read_json(p.cell.run_dir / "config.json")
        if not cfg:
            continue
        env = env or read_json(p.cell.run_dir / "env.json")
        key = p.cell.model.key
        if key in seen_models:
            continue
        seen_models.add(key)
        ident = cfg["identity"]["model"]
        serve = ident.get("serve")
        if serve:
            setting = ", ".join(f"{k}={v}" for k, v in serve.items())
        elif cfg["endpoint"].get("serve_settings_known"):
            setting = "-"
        else:
            setting = "설정 미상 (외부 endpoint)"
        rows.append([key, ident["model"], setting, str(cfg.get("sampling_sent")), str(cfg.get("server_default_sampling") or "-")])
    if rows:
        md += [_md_table(["model", "이름", "서빙 설정", "보낸 sampling", "서버 기본 sampling"], rows), ""]
    if env:
        gpu = ", ".join(f"{g['name']} {g['memory_total_mb'] / 1024:.0f}GB" for g in env.get("gpus", [])) or "없음"
        pk = env.get("packages", {})
        md += [
            f"- OS {env.get('os')}, Python {env.get('python')}, CPU {env.get('cpu')} ({env.get('cpu_threads')} threads), RAM {env.get('ram_gb')} GB",
            f"- GPU: {gpu} | Colab: {'예' if env.get('colab') else '아니오'}",
            f"- 패키지: " + ", ".join(f"{k} {v}" for k, v in pk.items() if v),
            f"- git commit: {(env.get('git', {}).get('commit') or '?')[:8]}" + (" (커밋 안 된 수정 있음)" if env.get("git", {}).get("dirty") else ""),
            "",
        ]
    md += ["run 폴더 (raw 결과)", ""]
    for p in plans:
        if p.records:
            md.append(f"- `{p.cell.run_dir.as_posix().split('/results/')[-1]}` : {p.cell.label}")
    md.append("")
    return md


def _write_html(out: Path, md_text: str, title: str) -> None:
    """이미지를 base64 로 넣은 단일 HTML. Colab 처럼 상대 경로 이미지가 안 보이는 환경용."""
    try:
        import markdown
    except ImportError:
        return

    def embed(m):
        p = out / m.group(1)
        if not p.is_file():
            return m.group(0)
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        mime = "image/jpeg" if p.suffix == ".jpg" else "image/png"
        return f'src="data:{mime};base64,{b64}"'

    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    body = re.sub(r'src="(figures/[^"]+)"', embed, body)
    css = (
        "body{font-family:system-ui,'Malgun Gothic',sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;line-height:1.5;color:#222;background:#fff}"
        "table{border-collapse:collapse;margin:12px 0;font-size:13px}th,td{border:1px solid #ccc;padding:4px 8px;text-align:left}"
        "th{background:#f2f2f2}img{max-width:100%}code{background:#f4f4f4;padding:1px 4px;border-radius:3px}"
    )
    html = f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{css}</style></head><body>{body}</body></html>"
    (out / "report.html").write_text(html, encoding="utf-8")
