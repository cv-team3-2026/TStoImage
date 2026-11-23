"""inner_filter chart: 그래프 안쪽만 바뀌고 축과 글자는 그대로인지."""
import numpy as np
import pytest

from ts2img import charts
from ts2img.benchmarks.base import Sample, Series
from ts2img.charts import inner_filter
from ts2img.config import expand, load_experiment
from ts2img.paths import EXPERIMENTS


def _sample(n, kind="generic"):
    rng = np.random.default_rng(0)
    series = [Series(f"s{i}", list(np.cumsum(rng.normal(size=64)) + i)) for i in range(n)]
    return Sample(id="t#0", unit="perception", task="perception/pattern_recognition", idx=0,
                  question="", answer="A", series=series, kind=kind)


def _arr(sample, **params):
    return np.asarray(charts.render(sample, "inner_filter", params)[0].pil().convert("RGB")).astype(int)


@pytest.mark.parametrize("n", [1, 2, 3])
@pytest.mark.parametrize("op", ["sharpen", "blur", "edge", "erode"])
def test_only_inside_changes(n, op):
    s = _sample(n)
    base, out = _arr(s, op="none"), _arr(s, op=op)
    assert base.shape == out.shape
    changed = np.abs(base - out).sum(axis=2) > 0
    assert changed.any()
    boxes = inner_filter._inner_boxes(s, 100, n)
    assert len(boxes) == n
    inside = np.zeros(changed.shape, dtype=bool)
    for left, top, right, bottom in boxes:
        assert not inside[top:bottom, left:right].any()   # 패널끼리 겹치지 않는다
        inside[top:bottom, left:right] = True
    assert not (changed & ~inside).any()          # 축선, 눈금, 글자는 그대로
    for left, top, right, bottom in boxes:        # 패널마다 선이 있으니 패널마다 바뀐다
        assert changed[top:bottom, left:right].any()


def test_none_has_no_grid_and_is_deterministic():
    s = _sample(1)
    a = charts.render(s, "inner_filter", {"op": "none"})[0]
    assert a.sha == charts.render(s, "inner_filter", {"op": "none"})[0].sha
    assert a.mime == "image/png"
    grid = np.asarray(charts.render(s, "line_style", {"fmt": "png"})[0].pil().convert("RGB")).astype(int)
    plain = np.asarray(a.pil().convert("RGB")).astype(int)
    assert grid.shape == plain.shape
    assert (grid != plain).any()


def test_erode_thickens_and_blur_softens():
    s = _sample(1)
    base, er, bl = _arr(s, op="none"), _arr(s, op="erode"), _arr(s, op="blur")
    dark = lambda a: int((a.sum(axis=2) < 600).sum())  # noqa: E731  흰색이 아닌 픽셀 수
    assert dark(er) > dark(base)
    assert dark(bl) > dark(base)
    assert er.min() <= base.min() + 5              # 침식은 선의 진한 색을 유지한다


def test_strength_changes_image_and_bad_values_fail():
    s = _sample(1)
    assert (_arr(s, op="erode", strength=1) != _arr(s, op="erode", strength=2)).any()
    with pytest.raises(ValueError):
        charts.render(s, "inner_filter", {"op": "canny"})
    with pytest.raises(ValueError):
        charts.render(s, "inner_filter", {"op": "blur", "strength": 0})


def test_abductive_renders():
    s = _sample(2, kind="abductive")
    s.split_index = 30
    for sr in s.series:
        sr.values = list(np.clip(np.abs(np.asarray(sr.values)) / 10, 0, 1))
    assert _arr(s, op="blur").shape == _arr(s, op="none").shape


def test_experiment_yaml():
    exp = load_experiment(EXPERIMENTS / "perception_kernel.yaml")
    assert [c.label for c in exp.charts] == ["nogrid", "sharpen", "blur", "edge"]
    assert exp.baseline_label() == "nogrid"
    assert len(expand(exp)) == 8  # chart 4 x (vision, text+vision)
