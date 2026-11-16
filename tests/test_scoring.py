import pytest

from ts2img.benchmarks.tsrbench.scoring import extract, score
from ts2img.report import stats


@pytest.mark.parametrize("response, expected", [
    ('{"reasoning": "x", "answer": "B"}', ("B", "json")),
    ('{"answer": "b"}', ("B", "json")),
    ('{"answer": "(C)"}', ("C", "json")),
    ('{"answer": "D. something"}', ("D", "json")),
    ("{'reasoning': 'x', 'answer': 'A'}", ("A", "json")),                    # python dict 표기
    ('```json\n{"reasoning": "x", "answer": "C"}\n```', ("C", "json")),      # code fence
    ('Sure. {"reasoning": "x", "answer": "A"} done', ("A", "json")),         # 앞뒤 설명
    ('{"reasoning": "x", "answer": ""}', (None, "json")),                    # dict 지만 답이 비어 있음
    ('{"reasoning": "x", "answer": "12"}', (None, "json")),
    ("B) because ...", ("B", "fallback")),
    ("The answer is C", ("C", "fallback")),
    ('"answer": "D"', ("D", "fallback")),                                    # 잘린 JSON
    ('{"reasoning": "x", "answer": "B"', ("B", "fallback")),                 # 닫는 괄호만 빠짐
    ('{"reasoning": "line1\nline2", "answer": "C"}', ("C", "fallback")),     # JSON 문법 오류(문자열 안 줄바꿈)지만 answer 항목은 있음
    # 길이 한도에서 잘린 풀이: 본문에 나온 글자를 답으로 집지 않는다 (Colab smoke 에서 실제로 나온 형태)
    ('{\n  "reasoning": "Option A: [[0, 1]]. So option C is incorrect.\\n\\nBut let\'s look at the time series again. River 175', (None, None)),
    ('{"reasoning": "I think the answer is B because the peaks', (None, None)),
    ('{"reasoning": "They wrote \\"answer\\": \\"A\\" earlier, but', (None, None)),
    ("Option A is wrong. The answer is B", ("B", "fallback")),               # 글로 답한 경우는 마지막 결론
    ("I am not sure.", (None, None)),
    ("", (None, None)),
    (None, (None, None)),
])
def test_extract(response, expected):
    assert extract(response) == expected


def test_score():
    assert score("B", '{"answer": "B"}').correct
    assert not score("B", '{"answer": "C"}').correct
    assert not score("B", "nothing").correct
    assert score("b", '{"answer": "B"}').correct


def test_no_eval():
    # 공식 코드는 eval() 을 쓴다. 여기서는 코드가 실행되면 안 된다
    assert extract("__import__('os').system('echo hacked')") == (None, None)


def test_wilson():
    lo, hi = stats.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert stats.wilson(0, 0) is None


def test_mcnemar_and_holm():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(10, 0) == pytest.approx(2 * 0.5 ** 10)
    assert stats.mcnemar_exact(5, 5) == 1.0
    adj = stats.holm([0.01, 0.04, 0.03])
    assert adj == pytest.approx([0.03, 0.06, 0.06])


def test_summarize_two_metrics():
    recs = [
        {"status": "ok", "correct": True, "parse": "json", "pred": "A"},
        {"status": "ok", "correct": False, "parse": "json", "pred": "B"},
        {"status": "ok", "correct": True, "parse": "fallback", "pred": "A"},   # 공식 채점은 제외
        {"status": "ok", "correct": False, "parse": None, "pred": None},        # 공식 채점은 제외
        {"status": "context_overflow", "correct": False},                       # 오답으로 집계
        {"status": "error", "correct": False},                                  # 집계 제외 (재시도 대상)
    ]
    s = stats.summarize(recs)
    assert s["n_ok"] == 4 and s["n_done"] == 5 and s["n_overflow"] == 1 and s["n_error"] == 1
    assert s["acc_official"] == pytest.approx(1 / 2)
    assert s["acc"] == pytest.approx(2 / 5)
