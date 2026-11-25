"""조합 chart 와 ablation 실험이 같은 full 그림을 가리키는지."""
import numpy as np

from ts2img import charts
from ts2img.benchmarks.base import Sample, Series
from ts2img.config import expand, load_experiment
from ts2img.paths import EXPERIMENTS


def _sample(n, kind="generic"):
    series = [Series(f"s{i}", [float(i), float(i + 3), 0.5, -float(i)]) for i in range(n)]
    return Sample(id="t#0", unit="perception", task="perception/similarity_analysis", idx=0,
                  question="", answer="A", series=series, kind=kind)


def _full(exp):
    return next(c for c in exp.charts if c.label == "full")


def test_ablation_full_is_shared():
    a = load_experiment(EXPERIMENTS / "perception_ablation.yaml")
    b = load_experiment(EXPERIMENTS / "perception_ablation_loo.yaml")
    assert _full(a).identity() == _full(b).identity()
    assert [c.label for c in b.charts] == [
        "full", "minus_panel_row", "minus_shared_y", "minus_scale",
        "minus_fade_grid", "minus_dark_mode", "minus_shade_jumps",
    ]
    cells = expand(a)
    assert len(cells) == 4  # baseline, full × vision, text+vision
    assert len(expand(b)) == 14


def test_row_changes_shape_and_one_series_ignores_layout():
    one = _sample(1)
    assert charts.render(one, "combo", {"layout": "row", "scale": 3, "shade": False})[0].sha == charts.render(
        one, "combo", {"layout": "stack", "scale": 3, "shade": False})[0].sha
    two = _sample(2)
    row = charts.render(two, "combo", {"layout": "row", "scale": 1, "share_y": False, "shade": False})[0]
    wide = charts.render(two, "combo", {"layout": "row", "scale": 3, "share_y": True, "shade": True})[0]
    stack = charts.render(two, "combo", {"layout": "stack", "scale": 1, "share_y": False, "shade": False})[0]
    assert row.size[0] > row.size[1]
    assert wide.size[0] > row.size[0] * 2
    assert stack.size[1] > row.size[1]
    shared = charts.render(two, "combo", {"layout": "row", "scale": 1, "share_y": True, "shade": False})[0]
    assert shared.sha != row.sha


def test_stack_scale_one_matches_baseline():
    sample = _sample(2)
    base = charts.render(sample, "tsrbench_baseline")[0]
    stack = charts.render(sample, "combo", {"layout": "stack", "share_y": False, "scale": 1, "shade": False})[0]
    assert base.sha == stack.sha


def test_dark_mode_runs_after_fade_grid():
    sample = _sample(2)
    img = charts.render(sample, "combo", {"layout": "row", "scale": 1, "shade": True}, ["fade_grid", "dark_mode"])[0]
    assert float(np.asarray(img.pil().convert("L")).mean()) < 80


def test_unknown_layout_rejected():
    try:
        charts.render(_sample(2), "combo", {"layout": "grid"})
    except ValueError as e:
        assert "layout" in str(e)
    else:
        raise AssertionError("layout 오류가 나야 한다")
