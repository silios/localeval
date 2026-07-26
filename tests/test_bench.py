"""Tests for localeval bench: throughput benchmark."""

import json

from localeval import bench
from localeval.__main__ import main
from localeval.client import ChatConfig


def test_run_benchmark_basic(monkeypatch):
    """Benchmark sends two non-streaming requests per trial: max_tokens=1
    to isolate pp_time, then the full generation for tg_time."""
    calls = []

    def fake_sync(config, messages):
        calls.append(config.max_tokens)
        if config.max_tokens == 1:
            return {"ok": True, "usage": {"prompt_tokens": 500, "completion_tokens": 1}, "elapsed_ms": 200.0}
        return {"ok": True, "usage": {"prompt_tokens": 500, "completion_tokens": 50}, "elapsed_ms": 700.0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    results = bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=100, tg_tokens=50, trials=1)

    assert len(results) == 1
    r = results[0]
    # pp: 500 tokens / 200ms = 2500 t/s
    # tg: 50 tokens / (700ms - 200ms) = 50 / 0.5 = 100 t/s
    assert r["depth"] == 0
    assert r["pp_tokens_per_sec"] == 2500.0
    assert r["tg_tokens_per_sec"] == 100.0
    assert r["pp_time_ms"] == 200.0
    assert r["total_ms"] == 700.0
    assert calls == [1, 50]  # step 1 uses max_tokens=1, step 2 uses tg_tokens


def test_run_benchmark_multiple_depths(monkeypatch):
    """Runs at each depth and reports per-depth results."""
    calls = []

    def fake_sync(config, messages):
        calls.append(1)
        if config.max_tokens == 1:
            return {"ok": True, "usage": {"prompt_tokens": 200, "completion_tokens": 1}, "elapsed_ms": 150.0}
        return {"ok": True, "usage": {"prompt_tokens": 200, "completion_tokens": 50}, "elapsed_ms": 600.0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    results = bench.run_benchmark(ChatConfig(), depths=[0, 4096, 8192], pp_tokens=200, tg_tokens=50, trials=1)

    assert len(results) == 3
    assert [r["depth"] for r in results] == [0, 4096, 8192]
    assert len(calls) == 6  # 2 requests per trial x 3 depths


def test_run_benchmark_multiple_trials(monkeypatch):
    """Multiple trials at each depth produce num_trials results."""
    def fake_sync(config, messages):
        if config.max_tokens == 1:
            return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 1}, "elapsed_ms": 100.0}
        return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 20}, "elapsed_ms": 300.0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    results = bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=100, tg_tokens=20, trials=3)

    assert len(results) == 3


def test_benchmark_uses_correct_payload(monkeypatch):
    """The benchmark sends pp_tokens of filler + requests tg_tokens, and
    both requests (pp probe and full generation) carry the same prompt."""
    captured_messages = []

    def fake_sync(config, messages):
        captured_messages.append(messages)
        completion_tokens = 1 if config.max_tokens == 1 else 50
        return {"ok": True, "usage": {"prompt_tokens": 500, "completion_tokens": completion_tokens}, "elapsed_ms": 500.0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=500, tg_tokens=50, trials=1)

    assert len(captured_messages) == 2
    msg = captured_messages[0][0]
    assert msg["role"] == "user"
    assert "benchmark" in msg["content"].lower() or "algorithm" in msg["content"].lower()
    assert captured_messages[0] == captured_messages[1]  # identical prompt in both requests


def test_each_trial_gets_a_unique_prompt_prefix(monkeypatch):
    """Every (depth, trial) pair must get a distinct prompt, so no
    backend's prefix/KV cache can be hit across trials - this is what
    keeps pp_tokens_per_sec honest on servers that ignore
    "cache_prompt": false (e.g. LM Studio), not just llama.cpp."""
    captured = []

    def fake_sync(config, messages):
        captured.append(messages[0]["content"])
        return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 1}, "elapsed_ms": 50.0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    bench.run_benchmark(ChatConfig(), depths=[0, 4096], pp_tokens=50, tg_tokens=10, trials=2)

    # 2 depths x 2 trials x 2 requests (pp probe + full gen) = 8 calls,
    # but only 4 distinct prompts (one per depth/trial pair, shared by
    # its two requests).
    assert len(captured) == 8
    assert len(set(captured)) == 4


def test_trial_nonce_is_at_the_start_of_the_prompt(monkeypatch):
    """A prefix/KV cache matches from byte zero - the nonce must be the
    very first thing in the content, not appended after shared filler/
    prompt text, or trials could still share a cacheable common prefix."""
    captured = []

    def fake_sync(config, messages):
        captured.append(messages[0]["content"])
        return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 1}, "elapsed_ms": 50.0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    bench.run_benchmark(ChatConfig(), depths=[4096], pp_tokens=50, tg_tokens=10, trials=2)

    trial_0_content, trial_1_content = captured[0], captured[2]
    assert trial_0_content.startswith("[bench ")
    common_prefix_len = 0
    for a, b in zip(trial_0_content, trial_1_content):
        if a != b:
            break
        common_prefix_len += 1
    # The two contents diverge inside the nonce label itself (at the
    # trial number) - a few characters in, not after the (potentially
    # thousands-of-tokens-long) filler/prompt body that follows it.
    assert 0 < common_prefix_len < 30
    assert common_prefix_len < len(trial_0_content) / 10


def test_run_benchmark_handles_error(monkeypatch):
    """A failed request still produces a result row with error flag."""
    def fake_sync(config, messages):
        return {"ok": False, "error": "connection refused", "elapsed_ms": 0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    results = bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=100, tg_tokens=50, trials=1)

    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["error"] == "connection refused"


def test_run_benchmark_marks_trial_invalid_when_pp_probe_is_slower_than_full_gen(monkeypatch):
    """If request 1 (max_tokens=1) comes back slower than request 2 (the
    full generation), the subtraction that derives tg_time_ms goes
    negative - the two requests' timings aren't comparable (jitter, not
    a real measurement). The trial must be marked invalid, not report a
    nonsense tg_tokens_per_sec from a floored near-zero tg_time."""
    def fake_sync(config, messages):
        if config.max_tokens == 1:
            return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 1}, "elapsed_ms": 300.0}
        return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 64}, "elapsed_ms": 250.0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    results = bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=100, tg_tokens=64, trials=1)

    assert len(results) == 1
    r = results[0]
    assert r["ok"] is False
    assert "invalid timing" in r["error"]
    assert r["pp_tokens_per_sec"] == 0.0
    assert r["tg_tokens_per_sec"] == 0.0


def test_summarize_excludes_invalid_timing_trials_from_medians():
    """A trial marked invalid by run_benchmark (ok=False, no real
    pp/tg numbers) must be excluded from the median the same way a
    connection failure is - not silently pull the median toward 0."""
    results = [
        {"depth": 0, "trial": 1, "pp_tokens": 0, "tg_tokens": 0, "pp_tokens_per_sec": 0.0,
         "tg_tokens_per_sec": 0.0, "ok": False, "error": "invalid timing: ..."},
        {"depth": 0, "trial": 2, "pp_tokens": 100, "tg_tokens": 64, "pp_tokens_per_sec": 2000.0,
         "tg_tokens_per_sec": 300.0, "ok": True, "error": ""},
    ]

    summary = bench.summarize(results)

    assert summary["error"] == 1
    assert summary["by_depth"]["0"]["errors"] == 1
    assert summary["by_depth"]["0"]["pp_tokens_per_sec_median"] == 2000.0
    assert summary["by_depth"]["0"]["tg_tokens_per_sec_median"] == 300.0


def test_summarize_computes_median_per_depth_and_overall():
    """summarize() takes the median (not mean) pp/tg t/s per depth and
    overall, so one stalled trial doesn't skew the reported number."""
    results = [
        {"depth": 0, "trial": 1, "pp_tokens": 100, "tg_tokens": 20, "pp_tokens_per_sec": 1000.0, "tg_tokens_per_sec": 100.0, "ok": True, "error": ""},
        {"depth": 0, "trial": 2, "pp_tokens": 100, "tg_tokens": 20, "pp_tokens_per_sec": 3000.0, "tg_tokens_per_sec": 300.0, "ok": True, "error": ""},
        {"depth": 4096, "trial": 1, "pp_tokens": 100, "tg_tokens": 20, "pp_tokens_per_sec": 2000.0, "tg_tokens_per_sec": 200.0, "ok": True, "error": ""},
    ]

    summary = bench.summarize(results)

    assert summary["total"] == 3
    assert summary["error"] == 0
    assert summary["by_depth"]["0"]["pp_tokens_per_sec_median"] == 2000.0  # median of 1000/3000
    assert summary["by_depth"]["0"]["tg_tokens_per_sec_median"] == 200.0
    assert summary["by_depth"]["4096"]["pp_tokens_per_sec_median"] == 2000.0
    assert summary["by_depth"]["4096"]["trials"] == 1


def test_summarize_excludes_errored_trials_from_medians():
    """An errored trial counts toward the error tally but never enters
    the pp/tg t/s medians (it has no real throughput to report)."""
    results = [
        {"depth": 0, "trial": 1, "pp_tokens": 0, "tg_tokens": 0, "pp_tokens_per_sec": 0.0, "tg_tokens_per_sec": 0.0, "ok": False, "error": "connection refused"},
        {"depth": 0, "trial": 2, "pp_tokens": 100, "tg_tokens": 20, "pp_tokens_per_sec": 1000.0, "tg_tokens_per_sec": 100.0, "ok": True, "error": ""},
    ]

    summary = bench.summarize(results)

    assert summary["total"] == 2
    assert summary["error"] == 1
    assert summary["by_depth"]["0"]["errors"] == 1
    assert summary["by_depth"]["0"]["pp_tokens_per_sec_median"] == 1000.0
    assert summary["pp_tokens_per_sec_median"] == 1000.0


def test_cmd_bench_persists_run_to_runs_dir(tmp_path, monkeypatch):
    """`localeval bench` must write config.json/results.jsonl/summary.json/
    a report under runs/bench/<ts>/, like every other mode - otherwise it
    can never be listed or compared."""
    def fake_sync(config, messages):
        if config.max_tokens == 1:
            return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 1}, "elapsed_ms": 100.0}
        return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 20}, "elapsed_ms": 300.0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    exit_code = main([
        "bench", "--runs-dir", str(tmp_path), "--pp", "100", "--tg", "20",
        "--depth", "0", "--trials", "2",
    ])
    assert exit_code == 0

    bench_dirs = list((tmp_path / "bench").iterdir())
    assert len(bench_dirs) == 1
    run_dir = bench_dirs[0]

    assert (run_dir / "config.json").exists()
    assert (run_dir / "results.jsonl").exists()
    assert (run_dir / "summary.json").exists()
    assert list(run_dir.glob("*-report.md"))

    cfg = json.loads((run_dir / "config.json").read_text())
    assert cfg["mode"] == "bench"

    results = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    assert len(results) == 2

    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["total"] == 2
    assert "0" in summary["by_depth"]
