"""Tests for localeval bench: throughput benchmark."""

from localeval import bench
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


def test_run_benchmark_handles_error(monkeypatch):
    """A failed request still produces a result row with error flag."""
    def fake_sync(config, messages):
        return {"ok": False, "error": "connection refused", "elapsed_ms": 0}

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)

    results = bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=100, tg_tokens=50, trials=1)

    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["error"] == "connection refused"
