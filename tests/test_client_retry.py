"""Tests for retry/backoff on transient request failures in chat_completion.

Retries must only apply to actual request failures (connection errors,
non-200 status, malformed JSON/shape) - never to a successful response,
including a truncated one (finish_reason == "length" is real signal, not
a transient fault, and must be returned as-is on the first attempt).
"""

import requests

from localeval import client
from localeval.client import ChatConfig, chat_completion


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


def test_retries_on_request_exception_then_succeeds(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise requests.RequestException("boom")
        return FakeResponse(json_data={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

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
            return FakeResponse(status_code=500, text="server error")
        return FakeResponse(json_data={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    monkeypatch.setattr(requests, "post", fake_post)
    config = ChatConfig(retries=2, retry_backoff=0)
    result = chat_completion(config, [])

    assert result.ok is True
    assert len(calls) == 2


def test_no_retry_on_successful_truncated_response(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        return FakeResponse(json_data={"choices": [{"message": {"content": "cut off"}, "finish_reason": "length"}]})

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
