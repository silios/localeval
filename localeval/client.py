"""Thin client for an OpenAI-compatible /v1/chat/completions endpoint."""

from __future__ import annotations

import dataclasses

import requests


@dataclasses.dataclass
class ChatConfig:
    base_url: str = "http://localhost:8080"
    model: str = ""
    api_key: str = ""
    max_tokens: int = 4096
    timeout: int = 120


@dataclasses.dataclass
class ChatResult:
    ok: bool
    content: str = ""
    finish_reason: str = ""
    raw_response: dict | None = None
    error: str = ""


def chat_completion(config: ChatConfig, messages: list[dict]) -> ChatResult:
    """Send a single chat completion request and return the outcome.

    Network/HTTP failures are captured in ChatResult.error rather than
    raised, so a single unreachable request does not abort a whole run.
    """
    url = config.base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload = {
        "messages": messages,
        "max_tokens": config.max_tokens,
    }
    if config.model:
        payload["model"] = config.model

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=config.timeout)
    except requests.RequestException as exc:
        return ChatResult(ok=False, error=f"request failed: {exc}")

    if resp.status_code != 200:
        return ChatResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:500]}")

    try:
        data = resp.json()
    except ValueError as exc:
        return ChatResult(ok=False, error=f"invalid JSON response: {exc}")

    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice.get("finish_reason", "")
    except (KeyError, IndexError, TypeError) as exc:
        return ChatResult(ok=False, error=f"unexpected response shape: {exc}", raw_response=data)

    return ChatResult(ok=True, content=content, finish_reason=finish_reason, raw_response=data)
