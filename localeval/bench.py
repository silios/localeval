"""Throughput benchmark: measures prompt processing and text generation
speed at configurable context depths.

Uses two non-streaming requests per trial, both against the same prompt:
1. max_tokens=1 - isolates prompt processing time, since generating a
   single token adds negligible time on top of processing the prompt.
2. max_tokens=tg_tokens - the full generation; its total elapsed time
   minus the pp_time measured in step 1 gives the generation time.

Both requests are non-streaming and hit the server with the identical
prompt, so their timings are directly comparable - unlike mixing a
streaming call's TTFT with a separate non-streaming call's total time,
which are two different requests measured two different ways.

Every trial's prompt is prefixed with a nonce unique to that (depth,
trial) pair, so no two trials ever share a prompt prefix. Without this,
a server that reuses a KV/prefix cache across requests (llama.cpp
without "cache_prompt": false, or any backend that ignores that
extension entirely - e.g. LM Studio) would let trial 2+ hit the cache
from trial 1's identical prompt, making pp_tokens_per_sec spike
unboundedly and invert across depths. "cache_prompt": false is still
sent for llama.cpp, but the nonce is what makes the fix portable to any
OpenAI-compatible backend regardless of whether it honors that field.

Because the two requests are independent round trips, request-to-
request timing jitter can occasionally make the max_tokens=1 probe
(request 1) come back slower than the full generation (request 2) -
especially on small/fast models where per-request overhead is
comparable to actual compute time. When that happens the trial is
marked invalid (status "error") rather than reporting a nonsense
tg_tokens_per_sec from a near-zero or negative subtraction.
"""

from __future__ import annotations

from .client import ChatConfig, chat_completion_sync


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

    Two non-streaming requests per trial, both sent with the identical
    prompt:
    1. max_tokens=1 -> elapsed_ms isolates prompt processing time (pp_time),
       since generating one token adds negligible time on top of it.
    2. max_tokens=tg_tokens -> elapsed_ms is the total time for prompt
       processing + full generation; tg_time is that total minus the
       pp_time measured in step 1.

    pp_tps = prompt_tokens / pp_time
    tg_tps = completion_tokens / tg_time
    """
    results = []

    for depth in depths:
        filler = _filler_text(depth) if depth > 0 else ""

        for trial in range(trials):
            nonce = f"[bench depth={depth} trial={trial}] "
            prompt_text = _bench_prompt(pp_tokens)

            if filler:
                content = nonce + filler + "\n\n" + prompt_text
            else:
                content = nonce + prompt_text

            messages = [{"role": "user", "content": content}]

            # --- Step 1: max_tokens=1 isolates prompt processing time ---
            pp_config = ChatConfig(
                base_url=config.base_url, model=config.model,
                api_key=config.api_key, max_tokens=1,
                timeout=config.timeout,
            )
            pp_resp = chat_completion_sync(pp_config, messages)
            pp_time_ms = pp_resp.get("elapsed_ms", 0)
            prompt_tokens = (pp_resp.get("usage") or {}).get("prompt_tokens", 0)
            pp_ok = pp_resp.get("ok", False)

            # --- Step 2: full generation ---
            tg_config = ChatConfig(
                base_url=config.base_url, model=config.model,
                api_key=config.api_key, max_tokens=tg_tokens,
                timeout=config.timeout,
            )
            tg_resp = chat_completion_sync(tg_config, messages)
            total_ms = tg_resp.get("elapsed_ms", 0)
            completion_tokens = (tg_resp.get("usage") or {}).get("completion_tokens", 0)
            tg_ok = tg_resp.get("ok", False)

            tg_time_ms = total_ms - pp_time_ms

            # If the isolated pp probe (request 1) came back slower than
            # the full generation call (request 2), the two requests'
            # timings aren't comparable - this is request-to-request
            # jitter, not a real measurement. Flooring tg_time_ms to some
            # minimum and reporting a number anyway produces nonsense
            # (e.g. 64 tokens / 0.001s = 64,000 t/s) - the same silent-
            # bad-number failure mode this project exists to catch, just
            # for throughput instead of correctness. Mark the whole trial
            # invalid instead: with the two requests inconsistent with
            # each other, neither half of the split is trustworthy.
            timing_valid = tg_time_ms > 0

            if timing_valid:
                pp_time_s = pp_time_ms / 1000
                tg_time_s = tg_time_ms / 1000
                pp_tps = prompt_tokens / pp_time_s if pp_time_s > 0 and prompt_tokens > 0 else 0.0
                tg_tps = completion_tokens / tg_time_s if tg_time_s > 0 and completion_tokens > 0 else 0.0
            else:
                pp_tps = 0.0
                tg_tps = 0.0

            ok = pp_ok and tg_ok and timing_valid
            error = pp_resp.get("error", "") or tg_resp.get("error", "")
            if pp_ok and tg_ok and not timing_valid:
                error = (
                    f"invalid timing: pp_time_ms ({pp_time_ms:.1f}) >= "
                    f"total_ms ({total_ms:.1f}) - request jitter, not a real measurement"
                )

            results.append({
                "depth": depth,
                "trial": trial + 1,
                "pp_tokens": prompt_tokens,
                "tg_tokens": completion_tokens,
                "pp_tokens_per_sec": round(pp_tps, 1),
                "tg_tokens_per_sec": round(tg_tps, 1),
                "pp_time_ms": round(pp_time_ms, 1),
                "total_ms": round(total_ms, 1),
                "ok": ok,
                "error": error,
            })

    return results


def _median(values: list) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def summarize(results: list) -> dict:
    """Aggregate per-trial results into overall and per-depth medians.

    Median (not mean) so a single stalled trial doesn't skew the
    reported throughput the way an outlier would skew a mean.
    """
    by_depth = {}
    for r in results:
        d = by_depth.setdefault(r["depth"], {"pp": [], "tg": [], "errors": 0, "trials": 0})
        d["trials"] += 1
        if r["ok"]:
            d["pp"].append(r["pp_tokens_per_sec"])
            d["tg"].append(r["tg_tokens_per_sec"])
        else:
            d["errors"] += 1

    by_depth_summary = {
        str(depth): {
            "trials": d["trials"],
            "errors": d["errors"],
            "pp_tokens_per_sec_median": round(_median(d["pp"]), 1),
            "tg_tokens_per_sec_median": round(_median(d["tg"]), 1),
        }
        for depth, d in by_depth.items()
    }

    all_pp = [r["pp_tokens_per_sec"] for r in results if r["ok"]]
    all_tg = [r["tg_tokens_per_sec"] for r in results if r["ok"]]

    return {
        "total": len(results),
        "error": sum(1 for r in results if not r["ok"]),
        "pp_tokens_per_sec_median": round(_median(all_pp), 1),
        "tg_tokens_per_sec_median": round(_median(all_tg), 1),
        "by_depth": by_depth_summary,
    }
