"""Tests for the quick/medium/long/ultra preset commands: `all` against
the bundled sample banks with a fixed --limit, so a sanity check doesn't
need --questions/--tasks-dir/--cases/--limit spelled out every time."""

import json

from localeval import bench, code, ifeval, mmlu
from localeval.__main__ import PRESET_BENCH_DEPTH, PRESET_LIMITS, main
from localeval.client import ChatResult


def test_preset_limits_are_ascending():
    """quick < medium < long, and ultra is unlimited (None) - a
    regression here would silently make a "bigger" tier run fewer items."""
    assert PRESET_LIMITS["quick"] < PRESET_LIMITS["medium"] < PRESET_LIMITS["long"]
    assert PRESET_LIMITS["ultra"] is None


def test_quick_preset_dry_run_uses_bundled_banks_and_limit(capsys):
    """--dry-run must not hit the server, and must report exactly
    PRESET_LIMITS['quick'] questions/tasks (ifeval's bundled bank is
    smaller than the limit, so all of it loads)."""
    exit_code = main(["quick", "--dry-run"])
    assert exit_code == 0

    out = capsys.readouterr().out
    assert f"{PRESET_LIMITS['quick']} questions loaded from sample_data/mmlu-test-bank-200.md" in out
    assert f"{PRESET_LIMITS['quick']} tasks loaded from sample_data/code_tasks" in out
    assert "cases loaded from sample_data/ifeval_sample.json" in out


def test_medium_preset_dry_run_uses_its_own_limit(capsys):
    exit_code = main(["medium", "--dry-run"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"{PRESET_LIMITS['medium']} questions loaded" in out


def test_long_preset_dry_run_uses_its_own_limit(capsys):
    exit_code = main(["long", "--dry-run"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"{PRESET_LIMITS['long']} questions loaded" in out


def test_ultra_preset_dry_run_has_no_limit(capsys):
    """ultra runs the full bundled banks - 200 mmlu questions, 29 code
    tasks - not a stride-sampled subset."""
    exit_code = main(["ultra", "--dry-run"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "200 questions loaded" in out
    assert "29 tasks loaded" in out


def test_preset_does_not_send_requests_in_dry_run(monkeypatch, capsys):
    """--dry-run on a preset must never call chat_completion, same
    guarantee as the underlying mmlu/code/ifeval --dry-run. Bench has no
    dry-run mode of its own, so it must be skipped entirely rather than
    silently hitting the server."""
    called = []

    def fake_chat(*args, **kwargs):
        called.append(1)

    monkeypatch.setattr("localeval.client.chat_completion", fake_chat)
    monkeypatch.setattr("localeval.client.chat_completion_sync", fake_chat)

    main(["quick", "--dry-run"])
    capsys.readouterr()
    assert len(called) == 0


def test_preset_runs_a_small_bench_before_the_capability_tests(tmp_path, monkeypatch, capsys):
    """Every preset (not --dry-run) must run a small throughput bench
    first and persist it under runs/bench/<ts>/, same as `localeval
    bench` on its own - this is what lets `list`/`compare` see it later."""
    def fake_sync(config, messages):
        if config.max_tokens == 1:
            return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 1}, "elapsed_ms": 50.0}
        return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 10}, "elapsed_ms": 150.0}

    def fake_chat(config, messages):
        return ChatResult(ok=True, content="FINAL ANSWER: A", finish_reason="stop")

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)
    monkeypatch.setattr(mmlu, "chat_completion", fake_chat)
    monkeypatch.setattr(code, "chat_completion", fake_chat)
    monkeypatch.setattr(ifeval, "chat_completion", fake_chat)

    main(["quick", "--base-url", "http://localhost:8080", "--runs-dir", str(tmp_path), "--max-tokens", "64", "--timeout", "5"])
    capsys.readouterr()

    bench_dirs = list((tmp_path / "bench").iterdir())
    assert len(bench_dirs) == 1
    bench_run_dir = bench_dirs[0]

    assert (bench_run_dir / "config.json").exists()
    assert (bench_run_dir / "summary.json").exists()

    summary = json.loads((bench_run_dir / "summary.json").read_text())
    depth_count = len(PRESET_BENCH_DEPTH.split(","))
    assert len(summary["by_depth"]) == depth_count

    assert list((tmp_path / "all").iterdir())  # mmlu/code/ifeval part still ran too
