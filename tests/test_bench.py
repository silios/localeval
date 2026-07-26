"""Tests for localeval bench: throughput benchmark."""

from localeval import bench
from localeval.client import ChatConfig, ChatResult


def test_run_benchmark_basic(monkeypatch):
    """Benchmark sends two requests per trial: sync for tokens, stream for timing."""
    sync_calls = []
    stream_calls = []

    def fake_sync(config, messages):
        sync_calls.append(1)
        return {"ok": True, "usage": {"prompt_tokens": 500, "completion_tokens": 50, "total_tokens": 550}, "elapsed_ms": 700.0}

    def fake_stream(config, messages):
        stream_calls.append(1)
        return ChatResult(ok=True, content="x" * 100, finish_reason="stop", ttft_ms=200.0)

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)
    monkeypatch.setattr(bench, "chat_completion", fake_stream)

    results = bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=100, tg_tokens=50, trials=1)

    assert len(results) == 1
    r = results[0]
    # pp: 500 tokens / 200ms TTFT = 2500 t/s
    # tg: 50 tokens / (700ms - 200ms) = 50 / 0.5 = 100 t/s
    assert r["depth"] == 0
    assert r["pp_tokens_per_sec"] == 2500.0
    assert r["tg_tokens_per_sec"] == 100.0
    assert r["ttft_ms"] == 200.0
    assert r["total_ms"] == 700.0
    assert len(sync_calls) == 1
    assert len(stream_calls) == 1


def test_run_benchmark_multiple_depths(monkeypatch):
    """Runs at each depth and reports per-depth results."""
    calls = []

    def fake_sync(config, messages):
        calls.append(1)
        return {"ok": True, "usage": {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250}, "elapsed_ms": 600.0}

    def fake_stream(config, messages):
        return ChatResult(ok=True, content="ok", finish_reason="stop", ttft_ms=150.0)

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)
    monkeypatch.setattr(bench, "chat_completion", fake_stream)

    results = bench.run_benchmark(ChatConfig(), depths=[0, 4096, 8192], pp_tokens=200, tg_tokens=50, trials=1)

    assert len(results) == 3
    assert [r["depth"] for r in results] == [0, 4096, 8192]
    assert len(calls) == 3


def test_run_benchmark_multiple_trials(monkeypatch):
    """Multiple trials at each depth produce num_trials results."""
    def fake_sync(config, messages):
        return {"ok": True, "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}, "elapsed_ms": 300.0}

    def fake_stream(config, messages):
        return ChatResult(ok=True, content="ok", finish_reason="stop", ttft_ms=100.0)

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)
    monkeypatch.setattr(bench, "chat_completion", fake_stream)

    results = bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=100, tg_tokens=20, trials=3)

    assert len(results) == 3


def test_benchmark_uses_correct_payload(monkeypatch):
    """The benchmark sends pp_tokens of filler + requests tg_tokens."""
    captured_messages = []

    def fake_sync(config, messages):
        captured_messages.append(messages)
        return {"ok": True, "usage": {"prompt_tokens": 500, "completion_tokens": 50, "total_tokens": 550}, "elapsed_ms": 500.0}

    def fake_stream(config, messages):
        return ChatResult(ok=True, content="x", finish_reason="stop", ttft_ms=100.0)

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)
    monkeypatch.setattr(bench, "chat_completion", fake_stream)

    bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=500, tg_tokens=50, trials=1)

    msg = captured_messages[0][0]
    assert msg["role"] == "user"
    assert "benchmark" in msg["content"].lower() or "algorithm" in msg["content"].lower()


def test_run_benchmark_handles_error(monkeypatch):
    """A failed request still produces a result row with error flag."""
    def fake_sync(config, messages):
        return {"ok": False, "error": "connection refused", "elapsed_ms": 0}

    def fake_stream(config, messages):
        return ChatResult(ok=False, error="stream failed")

    monkeypatch.setattr(bench, "chat_completion_sync", fake_sync)
    monkeypatch.setattr(bench, "chat_completion", fake_stream)

    results = bench.run_benchmark(ChatConfig(), depths=[0], pp_tokens=100, tg_tokens=50, trials=1)

    assert len(results) == 1
    assert results[0]["error"] == "connection refused"
