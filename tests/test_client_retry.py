"""Tests for retry/backoff on transient request failures in chat_completion.

Retries must only apply to actual request failures (connection errors,
non-200 status, malformed JSON/shape) - never to a successful response,
including a truncated one (finish_reason == "length" is real signal, not
a transient fault, and must be returned as-is on the first attempt).
"""

import json
import time

import requests

from localeval import client
from localeval.client import ChatConfig, ChatResult, _attempt, chat_completion


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


# ---------- SSE streaming helpers ----------

def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data)}"


class FakeStreamingResponse:
    """Simulates a requests.Response with iter_lines() yielding SSE events."""

    def __init__(self, status_code=200, sse_events=None):
        self.status_code = status_code
        self._events = sse_events or []

    def iter_lines(self, chunk_size=512, decode_unicode=False):
        for event in self._events:
            yield event

    def close(self):
        pass


def make_sse_chunk(delta_content=None, role=None, finish_reason=None, usage=None):
    """Build a single SSE choice dict."""
    choice = {"index": 0, "delta": {}, "finish_reason": finish_reason}
    if delta_content is not None:
        choice["delta"]["content"] = delta_content
    if role is not None:
        choice["delta"]["role"] = role
    chunk = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 1234567890,
        "model": "test-model",
        "choices": [choice],
    }
    if usage:
        chunk["usage"] = usage
    return chunk


# ---------- streaming + timing tests ----------


def test_streaming_accumulates_content_from_deltas(monkeypatch):
    """Content is built by concatenating delta.content from every SSE chunk."""
    events = [
        _sse_line(make_sse_chunk(role="assistant", delta_content="")),
        _sse_line(make_sse_chunk(delta_content="Hello")),
        _sse_line(make_sse_chunk(delta_content=" world")),
        _sse_line(make_sse_chunk(delta_content="!")),
        _sse_line(make_sse_chunk(finish_reason="stop", usage={"completion_tokens": 3, "prompt_tokens": 5, "total_tokens": 8})),
        "data: [DONE]",
    ]

    def fake_post(*args, **kwargs):
        return FakeStreamingResponse(sse_events=events)

    monkeypatch.setattr(requests, "post", fake_post)
    result = _attempt(ChatConfig(), [{"role": "user", "content": "hi"}])

    assert result.ok is True
    assert result.content == "Hello world!"
    assert result.finish_reason == "stop"
    assert result.total_tokens == 3


def test_streaming_sets_stream_true_in_payload(monkeypatch):
    """_attempt must send stream: true so the server responds with SSE."""
    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs.get("json", {})
        return FakeStreamingResponse(sse_events=[
            _sse_line(make_sse_chunk(delta_content="ok", finish_reason="stop")),
            "data: [DONE]",
        ])

    monkeypatch.setattr(requests, "post", fake_post)
    _attempt(ChatConfig(), [{"role": "user", "content": "hi"}])

    assert captured["json"].get("stream") is True


def test_streaming_captures_ttft(monkeypatch):
    """TTFT is measured from request start to first content delta."""
    events = [
        _sse_line(make_sse_chunk(role="assistant", delta_content="")),
        _sse_line(make_sse_chunk(delta_content="first token")),
        _sse_line(make_sse_chunk(finish_reason="stop", usage={"completion_tokens": 2, "prompt_tokens": 1, "total_tokens": 3})),
        "data: [DONE]",
    ]

    def fake_post(*args, **kwargs):
        return FakeStreamingResponse(sse_events=events)

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)  # fixed clock

    result = _attempt(ChatConfig(), [{"role": "user", "content": "hi"}])

    # With a fixed clock ttft is 0 (both reads at same time), but the
    # field must be present and non-negative.
    assert result.ttft_ms >= 0
    assert result.tokens_per_second >= 0


def test_streaming_timing_fields_present_on_chat_completion(monkeypatch):
    """chat_completion returns a ChatResult with the new timing fields."""
    events = [
        _sse_line(make_sse_chunk(delta_content="A")),
        _sse_line(make_sse_chunk(finish_reason="stop", usage={"completion_tokens": 1, "prompt_tokens": 1, "total_tokens": 2})),
        "data: [DONE]",
    ]

    def fake_post(*args, **kwargs):
        return FakeStreamingResponse(sse_events=events)

    monkeypatch.setattr(requests, "post", fake_post)
    result = chat_completion(ChatConfig(), [{"role": "user", "content": "hi"}])

    assert result.ttft_ms >= 0
    assert result.total_tokens == 1
    assert result.tokens_per_second >= 0


def test_streaming_reconstructs_raw_response(monkeypatch):
    """raw_response is shaped like a non-streaming /v1/chat/completions response."""
    events = [
        _sse_line(make_sse_chunk(delta_content="Hi")),
        _sse_line(make_sse_chunk(finish_reason="stop", usage={"completion_tokens": 1, "prompt_tokens": 5, "total_tokens": 6})),
        "data: [DONE]",
    ]

    def fake_post(*args, **kwargs):
        return FakeStreamingResponse(sse_events=events)

    monkeypatch.setattr(requests, "post", fake_post)
    result = _attempt(ChatConfig(model="test-model"), [{"role": "user", "content": "hi"}])

    assert result.raw_response is not None
    assert result.raw_response["object"] == "chat.completion"
    assert result.raw_response["model"] == "test-model"
    assert result.raw_response["choices"][0]["message"]["content"] == "Hi"
    assert result.raw_response["choices"][0]["finish_reason"] == "stop"
    assert result.raw_response["usage"]["completion_tokens"] == 1


def test_streaming_error_on_non_200(monkeypatch):
    """A non-200 streaming response is still treated as an error."""
    def fake_post(*args, **kwargs):
        return FakeStreamingResponse(status_code=500)

    monkeypatch.setattr(requests, "post", fake_post)
    result = _attempt(ChatConfig(), [{"role": "user", "content": "hi"}])

    assert result.ok is False
    assert "HTTP 500" in result.error


def test_retries_on_request_exception_then_succeeds(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise requests.RequestException("boom")
        return FakeStreamingResponse(sse_events=[
            _sse_line(make_sse_chunk(delta_content="ok", finish_reason="stop")),
            "data: [DONE]",
        ])

    monkeypatch.setattr(requests, "post", fake_post)
    config = ChatConfig(retries=2, retry_backoff=0)
    result = chat_completion(config, [])

    assert result.ok is True
    assert result.attempts == 3
    assert len(calls) == 3


def test_gives_up_after_exhausting_retries(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "post", fake_post)
    config = ChatConfig(retries=2, retry_backoff=0)
    result = chat_completion(config, [])

    assert result.ok is False
    assert result.attempts == 3
    assert len(calls) == 3


def test_retries_on_non_200_status(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) < 2:
            return FakeStreamingResponse(status_code=500)
        return FakeStreamingResponse(sse_events=[
            _sse_line(make_sse_chunk(delta_content="ok", finish_reason="stop")),
            "data: [DONE]",
        ])

    monkeypatch.setattr(requests, "post", fake_post)
    config = ChatConfig(retries=2, retry_backoff=0)
    result = chat_completion(config, [])

    assert result.ok is True
    assert len(calls) == 2


def test_no_retry_on_successful_truncated_response(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        return FakeStreamingResponse(sse_events=[
            _sse_line(make_sse_chunk(delta_content="cut off", finish_reason="length")),
            "data: [DONE]",
        ])

    monkeypatch.setattr(requests, "post", fake_post)
    config = ChatConfig(retries=2, retry_backoff=0)
    result = chat_completion(config, [])

    assert result.ok is True
    assert result.finish_reason == "length"
    assert result.attempts == 1
    assert len(calls) == 1


def test_default_zero_retries_makes_one_attempt(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "post", fake_post)
    result = chat_completion(ChatConfig(retry_backoff=0), [])

    assert result.ok is False
    assert len(calls) == ChatConfig().retries + 1
