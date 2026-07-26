"""Tests for localeval compare: side-by-side diff of two runs."""

from localeval.compare import diff_summaries


def test_diff_summaries_mmlu_identical():
    """Two identical summaries produce zero deltas."""
    a = {
        "total": 10, "correct": 8, "wrong": 2, "truncated": 0,
        "no_answer": 0, "error": 0, "accuracy_pct": 80.0,
        "by_category": {
            "math": {"accuracy_pct": 100.0, "correct": 5, "wrong": 0, "truncated": 0, "no_answer": 0, "error": 0},
            "history": {"accuracy_pct": 60.0, "correct": 3, "wrong": 2, "truncated": 0, "no_answer": 0, "error": 0},
        },
        "latency": {"ttft_p50_ms": 500.0, "ttft_p95_ms": 800.0, "tps_p50": 20.0, "tps_p95": 15.0, "timed_items": 10},
    }
    result = diff_summaries("mmlu", a, a)

    assert result["mode"] == "mmlu"
    assert result["overall"]["earned_delta"] == 0
    assert result["overall"]["total_delta"] == 0
    assert result["overall"]["pct_delta"] == 0.0
    assert result["categories"]["math"]["pct_delta"] == 0.0
    assert result["categories"]["history"]["pct_delta"] == 0.0


def test_diff_summaries_mmlu_improvement():
    """B improves over A - deltas should be positive."""
    a = {
        "total": 10, "correct": 6, "wrong": 4, "truncated": 0,
        "no_answer": 0, "error": 0, "accuracy_pct": 60.0,
        "by_category": {
            "math": {"accuracy_pct": 80.0, "correct": 4, "wrong": 1, "truncated": 0, "no_answer": 0, "error": 0},
        },
        "latency": {"ttft_p50_ms": 600.0, "ttft_p95_ms": 900.0, "tps_p50": 15.0, "tps_p95": 10.0, "timed_items": 5},
    }
    b = {
        "total": 10, "correct": 8, "wrong": 2, "truncated": 0,
        "no_answer": 0, "error": 0, "accuracy_pct": 80.0,
        "by_category": {
            "math": {"accuracy_pct": 100.0, "correct": 5, "wrong": 0, "truncated": 0, "no_answer": 0, "error": 0},
        },
        "latency": {"ttft_p50_ms": 400.0, "ttft_p95_ms": 600.0, "tps_p50": 20.0, "tps_p95": 15.0, "timed_items": 5},
    }
    result = diff_summaries("mmlu", a, b)

    assert result["overall"]["earned_delta"] == +2
    assert result["overall"]["pct_delta"] == +20.0
    assert result["categories"]["math"]["pct_delta"] == +20.0
    assert result["latency"]["ttft_p50_delta_ms"] == -200.0  # faster = negative
    assert result["latency"]["tps_p50_delta"] == +5.0  # more tokens/sec = positive


def test_diff_summaries_code_mode():
    """Code mode uses pass/fail instead of correct/wrong."""
    a = {"total": 5, "pass": 3, "fail": 2, "timeout": 0, "no_code_block": 0,
         "truncated": 0, "error": 0, "pass_rate_pct": 60.0,
         "latency": {}}
    b = {"total": 5, "pass": 5, "fail": 0, "timeout": 0, "no_code_block": 0,
         "truncated": 0, "error": 0, "pass_rate_pct": 100.0,
         "latency": {}}
    result = diff_summaries("code", a, b)

    assert result["mode"] == "code"
    assert result["overall"]["earned_delta"] == +2
    assert result["overall"]["pct_delta"] == +40.0


def test_diff_summaries_ifeval_mode():
    """IFEval mode uses pass/fail with by_constraint."""
    a = {
        "total": 6, "pass": 4, "fail": 2, "error": 0, "truncated": 0,
        "other": 0, "overall_pass_rate_pct": 66.7,
        "by_constraint": {
            "exact_word_count": {"pass_rate_pct": 100.0, "pass": 2, "fail": 0, "error": 0, "truncated": 0, "other": 0},
            "valid_json": {"pass_rate_pct": 50.0, "pass": 1, "fail": 1, "error": 0, "truncated": 0, "other": 0},
        },
        "latency": {},
    }
    b = {
        "total": 6, "pass": 5, "fail": 1, "error": 0, "truncated": 0,
        "other": 0, "overall_pass_rate_pct": 83.3,
        "by_constraint": {
            "exact_word_count": {"pass_rate_pct": 100.0, "pass": 2, "fail": 0, "error": 0, "truncated": 0, "other": 0},
            "valid_json": {"pass_rate_pct": 100.0, "pass": 2, "fail": 0, "error": 0, "truncated": 0, "other": 0},
        },
        "latency": {},
    }
    result = diff_summaries("ifeval", a, b)

    assert result["mode"] == "ifeval"
    assert result["overall"]["earned_delta"] == +1
    assert round(result["overall"]["pct_delta"], 1) == 16.6
    assert result["constraints"]["valid_json"]["pct_delta"] == +50.0
    assert result["constraints"]["exact_word_count"]["pct_delta"] == 0.0


def test_diff_handles_missing_latency():
    """When latency data is missing, deltas are not included."""
    a = {"total": 5, "correct": 3, "wrong": 2, "truncated": 0,
         "no_answer": 0, "error": 0, "accuracy_pct": 60.0, "by_category": {}}
    b = {"total": 5, "correct": 4, "wrong": 1, "truncated": 0,
         "no_answer": 0, "error": 0, "accuracy_pct": 80.0, "by_category": {}}
    result = diff_summaries("mmlu", a, b)

    assert result["latency"] == {}


def test_diff_handles_missing_categories():
    """If a category exists only in one summary, it still appears."""
    a = {"total": 5, "correct": 3, "wrong": 2, "truncated": 0,
         "no_answer": 0, "error": 0, "accuracy_pct": 60.0,
         "by_category": {"math": {"accuracy_pct": 100.0, "correct": 2, "wrong": 0, "truncated": 0, "no_answer": 0, "error": 0}}}
    b = {"total": 5, "correct": 4, "wrong": 1, "truncated": 0,
         "no_answer": 0, "error": 0, "accuracy_pct": 80.0,
         "by_category": {"math": {"accuracy_pct": 100.0, "correct": 2, "wrong": 0, "truncated": 0, "no_answer": 0, "error": 0},
                          "physics": {"accuracy_pct": 100.0, "correct": 2, "wrong": 0, "truncated": 0, "no_answer": 0, "error": 0}}}
    result = diff_summaries("mmlu", a, b)

    assert "physics" in result["categories"]
    assert result["categories"]["physics"]["pct_a"] == "-"
    assert result["categories"]["physics"]["pct_b"] == 100.0
