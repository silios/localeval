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
