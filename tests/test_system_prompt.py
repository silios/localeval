"""Tests for --system-prompt / --prompt-file override."""

import argparse
import pathlib

from localeval import __main__ as cli
from localeval import mmlu, code, ifeval
from localeval.client import ChatConfig, ChatResult


def test_mmlu_uses_configured_system_prompt(monkeypatch):
    """When system_prompt is set in config, it replaces the default."""
    q = mmlu.Question(
        id="q1", category="test", question="2+2?",
        options=["3", "4", "5", "6"], answer="B",
    )

    sent_messages = []

    def fake_chat(config, messages):
        sent_messages.extend(messages)
        return ChatResult(ok=True, content="FINAL ANSWER: B", finish_reason="stop")

    monkeypatch.setattr(mmlu, "chat_completion", fake_chat)

    config = ChatConfig(system_prompt="You are a math expert.")
    mmlu.evaluate_question(config, q)

    system_msg = sent_messages[0]
    assert system_msg["role"] == "system"
    assert system_msg["content"] == "You are a math expert."


def test_mmlu_uses_default_when_no_system_prompt(monkeypatch):
    """When system_prompt is empty, the built-in default is used."""
    q = mmlu.Question(
        id="q1", category="test", question="2+2?",
        options=["3", "4", "5", "6"], answer="B",
    )

    sent_messages = []

    def fake_chat(config, messages):
        sent_messages.extend(messages)
        return ChatResult(ok=True, content="FINAL ANSWER: B", finish_reason="stop")

    monkeypatch.setattr(mmlu, "chat_completion", fake_chat)

    config = ChatConfig()  # system_prompt defaults to ""
    mmlu.evaluate_question(config, q)

    system_msg = sent_messages[0]
    assert "FINAL ANSWER:" in system_msg["content"]  # default prompt


def test_code_uses_configured_system_prompt(monkeypatch, tmp_path):
    """Code mode uses configured system_prompt."""
    task = {
        "name": "test", "description": "Write hello world.",
        "verify_path": pathlib.Path("verify.py"), "filename": "solution.py",
    }

    sent_messages = []

    def fake_chat(config, messages):
        sent_messages.extend(messages)
        return ChatResult(ok=True, content="```python\nprint('hello')\n```", finish_reason="stop")

    monkeypatch.setattr(code, "chat_completion", fake_chat)

    config = ChatConfig(system_prompt="You write perfect Python.")
    code.run_task(config, task, tmp_path, verify_timeout=10)

    system_msg = sent_messages[0]
    assert system_msg["content"] == "You write perfect Python."


def test_ifeval_uses_configured_system_prompt(monkeypatch):
    """IFEval mode adds system message when system_prompt is set."""
    case = ifeval.Case(
        id="c1", prompt="Say hello.",
        constraint_type="exact_word_count", constraint_params={"n": 2},
    )

    sent_messages = []

    def fake_chat(config, messages):
        sent_messages.extend(messages)
        return ChatResult(ok=True, content="Hello world.", finish_reason="stop")

    monkeypatch.setattr(ifeval, "chat_completion", fake_chat)

    config = ChatConfig(system_prompt="Be brief.")
    ifeval.evaluate_case(config, case)

    # IFEval normally has no system prompt - first message should be user.
    # With system_prompt set, first message should be system.
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[0]["content"] == "Be brief."


def test_ifeval_no_system_prompt_default(monkeypatch):
    """IFEval mode without system_prompt still starts with user message."""
    case = ifeval.Case(
        id="c1", prompt="Say hello.",
        constraint_type="exact_word_count", constraint_params={"n": 2},
    )

    sent_messages = []

    def fake_chat(config, messages):
        sent_messages.extend(messages)
        return ChatResult(ok=True, content="Hello world.", finish_reason="stop")

    monkeypatch.setattr(ifeval, "chat_completion", fake_chat)

    config = ChatConfig()
    ifeval.evaluate_case(config, case)

    # No system prompt → first message is user
    assert sent_messages[0]["role"] == "user"


def test_run_config_dict_persists_system_prompt_and_api_key():
    """config.json must record system_prompt and api_key - resume rebuilds
    ChatConfig from this file, so anything missing here is silently lost
    on resume."""
    args = argparse.Namespace(
        base_url="http://localhost:8080", model="test-model", api_key="k-123",
        max_tokens=4096, timeout=120, concurrency=1, retries=2, retry_backoff=1.0,
        system_prompt="Custom prompt.", prompt_file=None,
    )
    config = cli.build_chat_config(args)
    cfg = cli.run_config_dict(args, "mmlu", config)

    assert cfg["system_prompt"] == "Custom prompt."
    assert cfg["api_key"] == "k-123"
