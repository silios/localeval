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
            chunk_finish = choice.get("finish_reason")

            if delta_role and not delta_content:
                # Role-only delta (e.g. {"role":"assistant","content":""}).
                # Don't count this as the first token.
                role = delta_role
            elif delta_content:
                if not first_content_seen:
                    ttft_ms = (time.monotonic() - t_start) * 1000
                    first_content_seen = True
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
