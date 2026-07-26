"""Tests for auto-discovering a server's base URL when --base-url isn't
given, and for accepting a bare host:port shorthand when it is."""

import argparse
import sys

import pytest
import requests

from localeval import client
from localeval.client import discover_base_url, discovery_hosts, normalize_base_url


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_normalize_base_url_adds_scheme_to_bare_host_port():
    assert normalize_base_url("192.168.1.50:8080") == "http://192.168.1.50:8080"


def test_normalize_base_url_leaves_existing_scheme_alone():
    assert normalize_base_url("http://localhost:8080") == "http://localhost:8080"
    assert normalize_base_url("https://example.com:443") == "https://example.com:443"


def test_normalize_base_url_is_case_insensitive_on_scheme():
    assert normalize_base_url("HTTP://localhost:8080") == "HTTP://localhost:8080"


def test_discover_base_url_returns_first_live_combination(monkeypatch):
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        if url == "http://localhost:8081/v1/models":
            return _FakeResponse(200)
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(client, "requests", type("R", (), {"get": staticmethod(fake_get), "RequestException": requests.RequestException}))

    result = discover_base_url(hosts=["localhost"], ports=(8080, 8081, 1234))

    assert result == "http://localhost:8081"
    assert calls == ["http://localhost:8080/v1/models", "http://localhost:8081/v1/models"]


def test_discover_base_url_tries_hosts_in_order_then_ports_within_each_host(monkeypatch):
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(client, "requests", type("R", (), {"get": staticmethod(fake_get), "RequestException": requests.RequestException}))

    discover_base_url(hosts=["localhost", "127.0.0.1"], ports=(8080, 1234))

    assert calls == [
        "http://localhost:8080/v1/models",
        "http://localhost:1234/v1/models",
        "http://127.0.0.1:8080/v1/models",
        "http://127.0.0.1:1234/v1/models",
    ]


def test_discover_base_url_returns_none_when_nothing_responds(monkeypatch):
    def fake_get(url, timeout):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(client, "requests", type("R", (), {"get": staticmethod(fake_get), "RequestException": requests.RequestException}))

    assert discover_base_url(hosts=["localhost"], ports=(8080,)) is None


def test_discover_base_url_ignores_non_200_responses(monkeypatch):
    def fake_get(url, timeout):
        return _FakeResponse(404)

    monkeypatch.setattr(client, "requests", type("R", (), {"get": staticmethod(fake_get), "RequestException": requests.RequestException}))

    assert discover_base_url(hosts=["localhost"], ports=(8080,)) is None


def test_discovery_hosts_includes_localhost_and_loopback_ip(monkeypatch):
    monkeypatch.setattr(client, "_local_nic_ip", lambda: None)
    hosts = discovery_hosts()
    assert hosts == ["localhost", "127.0.0.1"]


def test_discovery_hosts_appends_lan_ip_when_available(monkeypatch):
    monkeypatch.setattr(client, "_local_nic_ip", lambda: "192.168.1.42")
    hosts = discovery_hosts()
    assert hosts == ["localhost", "127.0.0.1", "192.168.1.42"]


def test_discovery_hosts_dedupes_lan_ip_matching_loopback(monkeypatch):
    monkeypatch.setattr(client, "_local_nic_ip", lambda: "127.0.0.1")
    hosts = discovery_hosts()
    assert hosts == ["localhost", "127.0.0.1"]


def test_build_chat_config_discovers_when_base_url_not_given(monkeypatch):
    from localeval.__main__ import build_chat_config

    monkeypatch.setattr("localeval.__main__.discover_base_url", lambda: "http://localhost:8081")

    args = argparse.Namespace(
        base_url=None, model="m", api_key="", max_tokens=4096, timeout=120,
        retries=2, retry_backoff=1.0, system_prompt=None, prompt_file=None,
    )
    config = build_chat_config(args)

    assert config.base_url == "http://localhost:8081"
    assert args.base_url == "http://localhost:8081"  # mutated so run_config_dict persists it


def test_build_chat_config_exits_when_discovery_finds_nothing(monkeypatch, capsys):
    from localeval.__main__ import build_chat_config

    monkeypatch.setattr("localeval.__main__.discover_base_url", lambda: None)

    args = argparse.Namespace(
        base_url=None, model="m", api_key="", max_tokens=4096, timeout=120,
        retries=2, retry_backoff=1.0, system_prompt=None, prompt_file=None,
    )
    with pytest.raises(SystemExit) as exc_info:
        build_chat_config(args)
    assert exc_info.value.code == 1
    assert "pass --base-url explicitly" in capsys.readouterr().err


def test_build_chat_config_normalizes_bare_host_port(monkeypatch):
    from localeval.__main__ import build_chat_config

    called = []
    monkeypatch.setattr("localeval.__main__.discover_base_url", lambda: (_ for _ in ()).throw(AssertionError("should not discover")))

    args = argparse.Namespace(
        base_url="192.168.1.50:8080", model="m", api_key="", max_tokens=4096, timeout=120,
        retries=2, retry_backoff=1.0, system_prompt=None, prompt_file=None,
    )
    config = build_chat_config(args)

    assert config.base_url == "http://192.168.1.50:8080"
    assert args.base_url == "http://192.168.1.50:8080"
