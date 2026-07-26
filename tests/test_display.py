"""Tests for localeval.display terminal rendering helpers."""

from localeval import display


def _run_row(run_dir: str) -> dict:
    return {
        "mode": "mmlu", "model": "test-model", "timestamp": "20260726T120000Z",
        "earned": 8, "total": 10, "score": "8/10", "rating": "★★★★☆ Good",
        "errors": 0, "run_dir": run_dir,
    }


def test_print_list_runs_trailer_path_default_runs_dir(capsys):
    """With the default `runs/<mode>/<timestamp>` layout, the trailer
    hint must point at `runs/<mode>/`."""
    display.print_list_runs([_run_row("runs/mmlu/20260726T120000Z")])
    out = capsys.readouterr().out
    assert "runs/mmlu/" in out


def test_print_list_runs_trailer_path_deep_runs_dir(capsys):
    """A --runs-dir several path segments deep must not have its own
    directory name truncated away - the hint is always run_dir's parent,
    not a fixed number of segments back from the end."""
    display.print_list_runs([_run_row("/tmp/scratch/my-custom-runs/mmlu/20260726T120000Z")])
    out = capsys.readouterr().out
    assert "/tmp/scratch/my-custom-runs/mmlu/" in out


def test_print_bench_results_is_a_single_bordered_panel(capsys):
    """The whole bench output - header, per-depth table, report link -
    must render inside one bordered box, matching the final-panel style
    every other mode uses, not a header panel plus a free-floating table."""
    results = [
        {"depth": 0, "trial": 1, "pp_tokens": 500, "tg_tokens": 64,
         "pp_tokens_per_sec": 2000.0, "tg_tokens_per_sec": 300.0, "total_ms": 400.0, "ok": True},
    ]
    display.print_bench_results(results, model="test-model", depths=[0], report_path="runs/bench/x/report.md")
    out = capsys.readouterr().out

    # A single top border line and a single bottom border line: the box
    # drawing corners appear exactly once each, meaning everything is
    # nested inside one Panel rather than two separate renderables.
    assert out.count("╭") == 1
    assert out.count("╰") == 1
    assert "Throughput Benchmark" in out
    assert "Report:" in out
    assert "d0" in out


def test_print_bench_results_incomplete_gets_red_border_and_warning_title(capsys):
    """A failed trial must flip the panel to the incomplete/red styling,
    same convention as print_final_panel's errored-run styling."""
    results = [
        {"depth": 0, "trial": 1, "ok": False, "error": "connection refused"},
    ]
    display.print_bench_results(results, model="test-model", depths=[0])
    out = capsys.readouterr().out
    assert "Incomplete" in out
    assert "connection refused" in out
