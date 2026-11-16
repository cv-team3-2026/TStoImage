"""task 선택, run 폴더 hash, 서빙 명령."""
import pytest

from ts2img import benchmarks
from ts2img.config import ChartSpec, ModelSpec, expand, load_experiment, load_models
from ts2img.paths import EXPERIMENTS


def _units(selectors):
    return [(s.unit, s.subtasks) for s in benchmarks.resolve(selectors)["tsrbench"]]


def test_select_hierarchy():
    assert len(_units(["tsrbench"])) == 12                      # 파일 12개 = task 15개 (perception 은 4개가 한 파일)
    assert len(benchmarks.get_benchmark("tsrbench").leaf_tasks()) == 15
    assert [u for u, _ in _units(["tsrbench/reasoning"])] == [
        "reasoning/abductive", "reasoning/causal", "reasoning/deductive", "reasoning/etiological",
        "reasoning/inductive", "reasoning/numerical", "reasoning/temporal_relation",
    ]
    assert _units(["tsrbench/perception"]) == [("perception", None)]
    assert _units(["tsrbench/perception/anomaly_detection"]) == [("perception", frozenset({"perception/anomaly_detection"}))]
    # 하위 task 두 개는 합쳐지고, 전체 선택이 있으면 전체가 우선한다
    two = _units(["tsrbench/perception/anomaly_detection", "tsrbench/perception/noise_understanding"])
    assert two == [("perception", frozenset({"perception/anomaly_detection", "perception/noise_understanding"}))]
    assert _units(["tsrbench/perception/anomaly_detection", "tsrbench/perception"]) == [("perception", None)]
    with pytest.raises(KeyError):
        _units(["tsrbench/nope"])


def test_shipped_experiments_load():
    names = sorted(p.stem for p in EXPERIMENTS.glob("*.yaml"))
    assert {"smoke", "perception_baseline", "perception_augment", "tsrbench_full_baseline"} <= set(names)
    models = load_models()
    for n in names:
        exp = load_experiment(EXPERIMENTS / f"{n}.yaml")
        assert expand(exp, models)
    # 공식 방식이 기본값: sampling 값을 보내지 않는다
    assert load_experiment(EXPERIMENTS / "perception_baseline.yaml").sampling_params() == {}
    assert len(expand(load_experiment(EXPERIMENTS / "tsrbench_full_baseline.yaml"), models)) == 12 * 2


def test_unknown_keys_rejected(make_exp):
    with pytest.raises(ValueError):
        make_exp(temperatur=0)
    with pytest.raises(ValueError):
        make_exp(charts=[{"use": "line_style", "linewidht": 3}])
    with pytest.raises(ValueError):
        make_exp(modalities=["image"])


def _cell(exp):
    return expand(exp)[0]


def test_hash_ignores_selection_and_runtime_options(make_exp):
    base = _cell(make_exp("a"))
    # 문항 선택과 실행 옵션은 답에 영향이 없으므로 같은 run 폴더를 쓴다
    for kw in ({"limit": 50}, {"concurrency": 1}, {"request_timeout": 30}, {"description": "x"},
               {"benchmarks": ["tsrbench/perception/anomaly_detection"]}):
        assert _cell(make_exp("b", **kw)).run_dir == base.run_dir, kw


def test_hash_changes_with_result_affecting_options(make_exp):
    base = _cell(make_exp("a"))
    for kw in ({"charts": [{"use": "line_style", "linewidth": 3}]}, {"charts": [{"use": "tsrbench_baseline", "post": ["sharpen"]}]},
               {"modalities": ["text+vision"]}, {"sampling": "deterministic"}, {"sampling": {"temperature": 0.7}},
               {"max_tokens": 512}, {"response_format": "none"}, {"answer_retries": 0},
               {"method": {"use": "single_turn", "image_captions": False}}):
        assert _cell(make_exp("b", **kw)).run_dir != base.run_dir, kw
    # text 조건에서만 의미가 있는 값도 hash 에는 들어간다 (단순한 규칙 유지)
    assert _cell(make_exp("b", text_stride=4)).hash != base.hash
    assert _cell(make_exp("b", ts_placeholder="[see image]")).hash != base.hash


def test_repeats_and_text_collapse(make_exp):
    exp = make_exp(modalities=["text", "vision"], charts=["tsrbench_baseline", {"use": "line_style", "linewidth": 4}], repeats=2)
    cells = expand(exp)
    # text 는 chart 와 무관: 1 x 2회, vision 은 chart 2 x 2회
    assert [(c.modality, c.chart.use, c.repeat) for c in cells] == [
        ("text", "none", 0), ("text", "none", 1),
        ("vision", "tsrbench_baseline", 0), ("vision", "tsrbench_baseline", 1),
        ("vision", "line_style", 0), ("vision", "line_style", 1),
    ]
    assert len({c.run_dir for c in cells}) == 6


def test_model_identity_ignores_operational_serve_keys():
    a = ModelSpec("m", "org/model", serve={"dtype": "float16", "port": 8000, "gpus": [0]})
    b = ModelSpec("m", "org/model", serve={"dtype": "float16", "port": 9999, "gpus": [1, 2]})
    c = ModelSpec("m", "org/model", serve={"dtype": "bfloat16", "port": 8000, "gpus": [0]})
    d = ModelSpec("m", "org/model", serve={"dtype": "float16", "quantization": "awq", "port": 8000})
    assert a.identity() == b.identity()
    assert a.identity() != c.identity() and a.identity() != d.identity()
    # context 한도는 한도 안의 문항 답을 바꾸지 않는다. 넘는 문항은 따로 기록하고 한도가 바뀌면 다시 시도한다
    e = ModelSpec("m", "org/model", serve={"dtype": "float16", "max_model_len": 32768})
    assert a.identity() == e.identity() and e.context_limit == 32768 and a.context_limit is None


def test_chart_label_and_slug():
    assert ChartSpec.parse("tsrbench_baseline").label == "tsrbench_baseline"
    spec = ChartSpec.parse({"use": "line_style", "linewidth": 4, "post": ["sharpen"]})
    assert spec.label == "line_style(linewidth=4)+sharpen"
    assert all(ch not in spec.slug for ch in '<>:"/\\|?* ()=,')
    assert ChartSpec.parse({"use": "line_style", "linewidth": 4, "label": "thick"}).label == "thick"


def test_serve_command():
    from ts2img.models import serve

    spec = load_models()["qwen3-vl-4b"]
    cmd, env = serve.build_command(spec, python="python")
    assert cmd[:3] == ["python", "-m", "vllm.entrypoints.openai.api_server"]
    opt = {cmd[i]: cmd[i + 1] for i in range(3, len(cmd) - 1) if cmd[i].startswith("--")}
    assert opt["--model"] == "Qwen/Qwen3-VL-4B-Instruct" and opt["--served-model-name"] == "Qwen/Qwen3-VL-4B-Instruct"
    assert opt["--dtype"] == "float16" and opt["--max-model-len"] == "8192"
    assert opt["--revision"] == spec.serve["revision"] and len(opt["--revision"]) == 40
    assert opt["--limit-mm-per-prompt"] == '{"image": 4}'
    assert env["CUDA_VISIBLE_DEVICES"] == "0"
    assert spec.resolved_base_url() == "http://127.0.0.1:8000/v1"

    multi = ModelSpec("m", "org/model", serve={"gpus": [0, 1], "quantization": "awq", "extra_args": ["--foo", 1]})
    cmd, env = serve.build_command(multi, python="python")
    assert env["CUDA_VISIBLE_DEVICES"] == "0,1"
    assert cmd[cmd.index("--tensor-parallel-size") + 1] == "2" and cmd[cmd.index("--quantization") + 1] == "awq"
    assert cmd[-2:] == ["--foo", "1"]
