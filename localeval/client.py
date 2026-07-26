"""Thin client for an OpenAI-compatible /v1/chat/completions endpoint.

Requests are sent with stream=True so we can measure time-to-first-token
(TTFT) and token throughput (tokens/sec), not just total wall-clock time.
The SSE event stream is parsed on the fly; a synthetic non-streaming
response dict is reconstructed and stored in ChatResult.raw_response so
every downstream consumer - results.jsonl, the report, the summary - sees
the same shape it always has.
"""

from __future__ import annotations

import dataclasses
import json
import time

import requests


@dataclasses.dataclass
class ChatConfig:
    base_url: str = "http://localhost:8080"
    model: str = ""
    api_key: str = ""
    max_tokens: int = 4096
    timeout: int = 120
    retries: int = 2
    retry_backoff: float = 1.0
    system_prompt: str = ""


@dataclasses.dataclass
class ChatResult:
    ok: bool
    content: str = ""
    finish_reason: str = ""
    raw_response: dict | None = None
    error: str = ""
    attempts: int = 1
    # Timing fields - populated only on a successful streaming response.
    ttft_ms: float = 0.0       # time from request to first content delta
    total_tokens: int = 0      # completion_tokens from the final usage chunk
    tokens_per_second: float = 0.0  # total_tokens / (end_time - ttft)


def _parse_sse_stream(resp) -> ChatResult:
    """Parse a streaming (SSE) response into a ChatResult.

    Accumulates content from delta.content events, captures the first
    non-empty content timestamp for TTFT, and picks up finish_reason +
    usage from the final chunk. Also reconstructs the equivalent
    non-streaming response dict as raw_response, so downstream code
    (results.jsonl, reports) sees the shape it always has.
    """
    content_parts: list[str] = []
    finish_reason = ""
    usage = {}
    chunk_id = ""
    model = ""
    created = 0
    role = "assistant"

    t_start = time.monotonic()
    ttft_ms = 0.0
    first_content_seen = False

    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if not line.startswith("data: "):
            continue
        data_str = line[6:]  # strip "data: " prefix
        if data_str == "[DONE]":
            break

        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        # Capture metadata from any chunk (first one usually carries it).
        if not chunk_id:
            chunk_id = chunk.get("id", "")
        if not model:
            model = chunk.get("model", "")
        if not created:
            created = chunk.get("created", 0)

        if "usage" in chunk:
            usage = chunk["usage"]

        choices = chunk.get("choices", [])
        if choices:
            choice = choices[0]
            delta = choice.get("delta", {})
            delta_role = delta.get("role", "")
            delta_content = delta.get("content", "")
            delta_reasoning = delta.get("reasoning_content", "")
            chunk_finish = choice.get("finish_reason")

            if delta_role and not delta_content and not delta_reasoning:
                # Role-only delta (e.g. {"role":"assistant","content":""}).
                role = delta_role
            elif delta_content or delta_reasoning:
                if not first_content_seen:
                    ttft_ms = (time.monotonic() - t_start) * 1000
                    first_content_seen = True
                if delta_content:
                    content_parts.append(delta_content)

            if chunk_finish:
                finish_reason = chunk_finish

    t_end = time.monotonic()

    content = "".join(content_parts)
    completion_tokens = usage.get("completion_tokens", 0)
    prompt_tokens = usage.get("prompt_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    # Tokens-per-second: decode time only (exclude TTFT).
    decode_duration_s = t_end - t_start - (ttft_ms / 1000)
    tokens_per_second = completion_tokens / decode_duration_s if decode_duration_s > 0 and completion_tokens > 0 else 0.0

    # Reconstruct a synthetic non-streaming response so raw_response
    # always has the same shape regardless of transport.
    synthetic = {
        "id": chunk_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": role, "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "completion_tokens": completion_tokens,
            "prompt_tokens": prompt_tokens,
            "total_tokens": total_tokens,
        },
    }

    return ChatResult(
        ok=True,
        content=content,
        finish_reason=finish_reason,
        raw_response=synthetic,
        ttft_ms=round(ttft_ms, 1),
        total_tokens=completion_tokens,
        tokens_per_second=round(tokens_per_second, 1),
    )


def _attempt(config: ChatConfig, messages: list[dict]) -> ChatResult:
    url = config.base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload = {
        "messages": messages,
        "max_tokens": config.max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if config.model:
        payload["model"] = config.model

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=config.timeout, stream=True)
    except requests.RequestException as exc:
        return ChatResult(ok=False, error=f"request failed: {exc}")

    if resp.status_code != 200:
        error_text = ""
        try:
            error_text = resp.text[:500]
        except Exception:
            pass
        return ChatResult(ok=False, error=f"HTTP {resp.status_code}: {error_text}")

    try:
        return _parse_sse_stream(resp)
    except Exception as exc:
        return ChatResult(ok=False, error=f"SSE parse error: {exc}")


def chat_completion(config: ChatConfig, messages: list[dict]) -> ChatResult:
    """Send a chat completion request, retrying on transient request failures.

    Requests are sent with stream=True so TTFT and tokens/sec can be
    measured. The SSE event stream is parsed on the fly and a synthetic
    non-streaming response dict is stored as raw_response, so every
    downstream consumer (results.jsonl, reports, summary) sees the same
    shape it always has.

    Retries only apply when the request itself failed (network error,
    non-200 status, SSE parse error) - a successful response is never
    retried, including one with finish_reason == "length": that is real
    signal about the model's output, not a transient fault, and must be
    returned as-is. Network/HTTP failures are captured in
    ChatResult.error rather than raised, so a single unreachable request
    does not abort a whole run.
    """
    for attempt in range(1, config.retries + 2):
        result = _attempt(config, messages)
        result.attempts = attempt
        if result.ok or attempt == config.retries + 1:
            return result
        if config.retry_backoff > 0:
            time.sleep(config.retry_backoff * (2 ** (attempt - 1)))


def chat_completion_sync(config: ChatConfig, messages: list[dict]) -> dict:
    """Send a single non-streaming request and return usage + timing.

    Used by the throughput benchmark (localeval bench) where we need
    prompt_tokens and completion_tokens from the usage block - data
    that llama.cpp does not send in streaming SSE mode.

    Sends "cache_prompt": false, a llama.cpp server extension (ignored
    by strictly OpenAI-compatible backends as an unknown field). Without
    it, back-to-back bench trials against the same prompt hit llama.cpp's
    prompt-prefix cache on the second and later calls, making pp_time
    collapse toward zero and pp_tokens_per_sec spike unboundedly - each
    trial needs a genuine cold prompt pass to be a valid measurement.

    Returns a dict with: ok, content, usage, elapsed_ms, error.
    Does NOT retry (bench failures are informational, not retryable).
    """
    url = config.base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload = {
        "messages": messages,
        "max_tokens": config.max_tokens,
        "stream": False,
        "cache_prompt": False,
    }
    if config.model:
        payload["model"] = config.model

    t0 = time.monotonic()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=config.timeout)
    except requests.RequestException as exc:
        return {"ok": False, "error": f"request failed: {exc}", "elapsed_ms": 0}

    elapsed_ms = (time.monotonic() - t0) * 1000

    if resp.status_code != 200:
        return {"ok": False, "error": f"HTTP {resp.status_code}", "elapsed_ms": elapsed_ms}

    try:
        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = data.get("usage", {})
        return {
            "ok": True,
            "content": content,
            "usage": usage,
            "elapsed_ms": round(elapsed_ms, 1),
        }
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        return {"ok": False, "error": f"bad response: {exc}", "elapsed_ms": elapsed_ms}
