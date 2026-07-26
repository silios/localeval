"""Tests for localeval list-runs: navigating past run directories."""

import json
import pathlib

from localeval.__main__ import list_runs


def _make_run(runs_root: pathlib.Path, mode: str, ts: str, model: str,
              earned: int, total: int, pct: float, errors: int = 0) -> pathlib.Path:
    """Create a minimal synthetic run directory for testing."""
    run_dir = runs_root / mode / ts
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps({
        "mode": mode, "model": model, "base_url": "http://localhost:8080",
    }))
    summary = {
        "total": total, "error": errors,
        "truncated": 0, "no_answer": 0, "timeout": 0, "no_code_block": 0, "other": 0,
    }
    if mode == "mmlu":
        summary["correct"] = earned
        summary["wrong"] = total - earned
        summary["accuracy_pct"] = pct
    elif mode == "code":
        summary["pass"] = earned
        summary["fail"] = total - earned
        summary["pass_rate_pct"] = pct
    else:
        summary["pass"] = earned
        summary["fail"] = total - earned
        summary["overall_pass_rate_pct"] = pct
    (run_dir / "summary.json").write_text(json.dumps(summary))
    return run_dir


def test_list_runs_returns_all_runs(tmp_path):
    """list_runs finds all run directories with config.json + summary.json."""
    _make_run(tmp_path, "mmlu", "20260726T120000Z", "model-a", 8, 10, 80.0)
    _make_run(tmp_path, "code", "20260726T130000Z", "model-b", 3, 5, 60.0)
    _make_run(tmp_path, "ifeval", "20260726T140000Z", "model-c", 4, 6, 66.7)

    runs = list_runs(tmp_path)

    assert len(runs) == 3
    modes = {r["mode"] for r in runs}
    assert modes == {"mmlu", "code", "ifeval"}


def test_list_runs_skips_incomplete_dirs(tmp_path):
    """Directories without summary.json are skipped."""
    _make_run(tmp_path, "mmlu", "20260726T120000Z", "model-a", 8, 10, 80.0)
    # Create a dir with config.json but no summary.json (incomplete run)
    incomplete = tmp_path / "mmlu" / "20260726T130000Z"
    incomplete.mkdir(parents=True)
    (incomplete / "config.json").write_text(json.dumps({"mode": "mmlu"}))

    runs = list_runs(tmp_path)
    assert len(runs) == 1


def test_list_runs_includes_score_and_rating(tmp_path):
    """Each run entry includes score, pct, and a rating label."""
    _make_run(tmp_path, "mmlu", "20260726T120000Z", "test-model", 9, 10, 90.0)

    runs = list_runs(tmp_path)
    r = runs[0]

    assert r["mode"] == "mmlu"
    assert r["model"] == "test-model"
    assert r["earned"] == 9
    assert r["total"] == 10
    assert r["pct"] == 90.0
    assert "Excellent" in r["rating"]


def test_list_runs_filters_by_model(tmp_path):
    """Filter shows only runs matching the model glob."""
    _make_run(tmp_path, "mmlu", "20260726T120000Z", "qwen-7b", 8, 10, 80.0)
    _make_run(tmp_path, "mmlu", "20260726T130000Z", "llama-8b", 6, 10, 60.0)
    _make_run(tmp_path, "code", "20260726T140000Z", "qwen-7b", 3, 5, 60.0)

    runs = list_runs(tmp_path, model_filter="qwen*")
    assert len(runs) == 2
    assert all("qwen" in r["model"] for r in runs)


def test_list_runs_sorted_by_timestamp(tmp_path):
    """Runs are returned sorted by timestamp, newest first."""
    _make_run(tmp_path, "mmlu", "20260726T120000Z", "model-a", 8, 10, 80.0)
    _make_run(tmp_path, "mmlu", "20260726T140000Z", "model-b", 6, 10, 60.0)
    _make_run(tmp_path, "mmlu", "20260726T130000Z", "model-c", 7, 10, 70.0)

    runs = list_runs(tmp_path)
    # Newest first
    assert runs[0]["timestamp"] == "20260726T140000Z"
    assert runs[1]["timestamp"] == "20260726T130000Z"
    assert runs[2]["timestamp"] == "20260726T120000Z"


def test_list_runs_empty_directory(tmp_path):
    """An empty runs directory returns an empty list."""
    runs = list_runs(tmp_path)
    assert runs == []


def test_list_runs_includes_bench_runs(tmp_path):
    """Bench runs show up in `list` with a throughput score, not a
    pass/fail score - score_fields() doesn't know how to score "bench"."""
    run_dir = tmp_path / "bench" / "20260727T010000Z"
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps({
        "mode": "bench", "model": "test-model", "base_url": "http://localhost:8080",
    }))
    (run_dir / "summary.json").write_text(json.dumps({
        "total": 4, "error": 0,
        "pp_tokens_per_sec_median": 3456.0, "tg_tokens_per_sec_median": 210.5,
        "by_depth": {},
    }))

    runs = list_runs(tmp_path)

    assert len(runs) == 1
    r = runs[0]
    assert r["mode"] == "bench"
    assert r["rating"] == "-"
    assert "3456" in r["score"] and "210" in r["score"]


def test_list_runs_handles_errors_gracefully(tmp_path):
    """Runs with error counts show the errored badge."""
    _make_run(tmp_path, "mmlu", "20260726T120000Z", "model-a", 5, 10, 50.0, errors=3)

    runs = list_runs(tmp_path)
    r = runs[0]
    assert r["errors"] == 3
