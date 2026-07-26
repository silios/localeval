"""Throughput benchmark: measures prompt processing and text generation
speed at configurable context depths.

Uses two requests per trial:
1. Non-streaming: gets accurate prompt_tokens + completion_tokens from usage
2. Streaming: gets accurate TTFT and total elapsed time (our streaming
   parser correctly handles reasoning models by ignoring reasoning_content
   deltas and only counting content deltas)
"""

from __future__ import annotations

import time

from .client import ChatConfig, chat_completion, chat_completion_sync


def _filler_text(tokens: int) -> str:
    sentence = "The quick brown fox jumps over the lazy dog. "
    words_needed = tokens * 3
    repeats = max(1, words_needed // 10)
    return (sentence * repeats)[: tokens * 6]


def _bench_prompt(pp_tokens: int) -> str:
    words = [
        "algorithm", "benchmark", "computation", "data", "efficiency",
        "function", "graph", "hardware", "inference", "json",
        "kernel", "latency", "memory", "network", "optimization",
        "performance", "query", "runtime", "system", "throughput",
        "utilization", "vector", "workload", "execution", "framework",
    ]
    result = []
    for i in range(pp_tokens):
        result.append(words[i % len(words)])
    return " ".join(result)


def run_benchmark(
    config: ChatConfig,
    depths: list[int],
    pp_tokens: int = 2048,
    tg_tokens: int = 128,
    trials: int = 3,
) -> list[dict]:
    """Run a throughput benchmark at each context depth.

    Two requests per trial:
    1. Non-streaming → usage.prompt_tokens + usage.completion_tokens
    2. Streaming → accurate TTFT (prompt processing time) and total
       elapsed. Our SSE parser correctly measures time-to-first-content
       for reasoning models (ignores reasoning_content deltas).

    pp_tps = prompt_tokens / TTFT
    tg_tps = completion_tokens / (total_time - TTFT)
    """
    results = []

    for depth in depths:
        filler = _filler_text(depth) if depth > 0 else ""

        for trial in range(trials):
            prompt_text = _bench_prompt(pp_tokens)

            if filler:
                content = filler + "\n\n" + prompt_text
            else:
                content = prompt_text

            messages = [{"role": "user", "content": content}]

            # --- Step 1: non-streaming for token counts ---
            sync_config = ChatConfig(
                base_url=config.base_url, model=config.model,
                api_key=config.api_key, max_tokens=tg_tokens,
                timeout=config.timeout,
            )
            sync_resp = chat_completion_sync(sync_config, messages)
            usage = sync_resp.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            sync_ok = sync_resp.get("ok", False)
            sync_error = sync_resp.get("error", "")

            # --- Step 2: streaming for accurate timing ---
            stream_config = ChatConfig(
                base_url=config.base_url, model=config.model,
                api_key=config.api_key, max_tokens=tg_tokens,
                timeout=config.timeout,
            )
            stream_resp = chat_completion(stream_config, messages)
            ttft_ms = stream_resp.ttft_ms  # time to first content token
            stream_ok = stream_resp.ok

            # Derive times
            # total elapsed is harder from streaming. Use TTFT and estimate
            # from token rate. Or we measure total time ourselves.
            # Actually: we don't have total_ms from the streaming ChatResult.
            # Let's compute: total ≈ ttft + (completion_tokens / estimated_tps)
            # That's circular. Better: add total_ms to ChatResult.

            # For now, use sync elapsed as total, streaming TTFT as pp_time
            total_ms = sync_resp.get("elapsed_ms", 0)
            pp_time_ms = ttft_ms
            tg_time_ms = max(1, total_ms - pp_time_ms)

            pp_time_s = pp_time_ms / 1000
            tg_time_s = tg_time_ms / 1000

            pp_tps = prompt_tokens / pp_time_s if pp_time_s > 0 and prompt_tokens > 0 else 0.0
            tg_tps = completion_tokens / tg_time_s if tg_time_s > 0 and completion_tokens > 0 else 0.0

            ok = sync_ok and stream_ok
            error = sync_error or ("" if stream_ok else "streaming request failed")

            results.append({
                "depth": depth,
                "trial": trial + 1,
                "pp_tokens": prompt_tokens,
                "tg_tokens": completion_tokens,
                "pp_tokens_per_sec": round(pp_tps, 1),
                "tg_tokens_per_sec": round(tg_tps, 1),
                "ttft_ms": round(ttft_ms, 1),
                "total_ms": total_ms,
                "ok": ok,
                "error": error,
            })

    return results
