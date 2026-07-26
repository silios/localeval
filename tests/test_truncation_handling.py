"""Tests for the finish_reason == "length" -> TRUNCATED handling in
`code` and `ifeval` modes. mmlu already had this covered
(test_evaluate_question_marks_truncated_even_if_answer_pattern_present);
code and ifeval originally did not check finish_reason at all, so a
truncated response could be silently scored fail/pass - the same class
of bug that produced a false 22.8% MMLU score in a previous harness.
"""

import pathlib

from localeval import code, ifeval
from localeval.client import ChatConfig, ChatResult


def test_code_task_marks_truncated_even_if_code_block_looks_complete(tmp_path, monkeypatch):
    task = {
        "name": "reverse-string",
        "description": "Write a function that reverses a string.",
        "verify_path": pathlib.Path("verify.py"),
        "filename": "solution.py",
    }

    def fake_chat_completion(config, messages):
        return ChatResult(
            ok=True,
            content="```python\ndef reverse_string(s):\n    return s[::-1]\n```",
            finish_reason="length",
        )

    monkeypatch.setattr(code, "chat_completion", fake_chat_completion)

    result = code.run_task(ChatConfig(), task, tmp_path, verify_timeout=10)
    assert result["status"] == "truncated"
    # a truncated response must never be written to disk and verified -
    # that would silently produce a fail/pass verdict on partial code.
    assert not (tmp_path / task["name"] / task["filename"]).exists()


def test_ifeval_case_marks_truncated_even_if_constraint_would_pass(monkeypatch):
    # "no_commas" is trivially satisfied by truncated text with no comma
    # yet - this must not be allowed to count as a pass.
    case = ifeval.Case(id="c1", prompt="Write something.", constraint_type="no_commas", constraint_params={})

    def fake_chat_completion(config, messages):
        return ChatResult(ok=True, content="This response got cut off mid", finish_reason="length")

    monkeypatch.setattr(ifeval, "chat_completion", fake_chat_completion)

    result = ifeval.evaluate_case(ChatConfig(), case)
    assert result["status"] == "truncated"


def test_ifeval_case_normal_pass_and_fail_unaffected(monkeypatch):
    case = ifeval.Case(id="c1", prompt="...", constraint_type="no_commas", constraint_params={})

    def fake_stop_pass(config, messages):
        return ChatResult(ok=True, content="no commas here", finish_reason="stop")

    monkeypatch.setattr(ifeval, "chat_completion", fake_stop_pass)
    result = ifeval.evaluate_case(ChatConfig(), case)
    assert result["status"] == "pass"

    def fake_stop_fail(config, messages):
        return ChatResult(ok=True, content="this, has a comma", finish_reason="stop")

    monkeypatch.setattr(ifeval, "chat_completion", fake_stop_fail)
    result = ifeval.evaluate_case(ChatConfig(), case)
    assert result["status"] == "fail"
