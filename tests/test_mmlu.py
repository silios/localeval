"""Tests for the MMLU answer-extraction logic - the part that broke the
previous eval harness (truncated generations + first-letter-token matching
against echoed multiple-choice options)."""

from localeval import mmlu
from localeval.client import ChatConfig, ChatResult


def test_extract_simple_final_answer():
    text = "Let's think step by step. 7 + 5 = 12.\nFINAL ANSWER: C"
    status, letter = mmlu.extract_final_answer(text)
    assert status == "answered"
    assert letter == "C"


def test_extract_ignores_echoed_options_takes_last_match():
    # The model restates the options (which look like "B. 1", "C. 0,1" etc.)
    # before giving its real answer. Only the true FINAL ANSWER: line
    # should be picked, not the first letter-like token in the text.
    text = (
        "Options: A. 0, B. 1, C. 0,1, D. 0,4\n"
        "Thinking it through...\n"
        "FINAL ANSWER: C"
    )
    status, letter = mmlu.extract_final_answer(text)
    assert status == "answered"
    assert letter == "C"


def test_extract_takes_last_of_multiple_final_answer_lines():
    text = "FINAL ANSWER: B\nActually wait, reconsidering...\nFINAL ANSWER: D"
    status, letter = mmlu.extract_final_answer(text)
    assert status == "answered"
    assert letter == "D"


def test_extract_buried_mid_response():
    text = (
        "Some long reasoning here about the problem. "
        "FINAL ANSWER: B is what I conclude, though let me add a caveat "
        "that this depends on assumptions not stated in the question."
    )
    status, letter = mmlu.extract_final_answer(text)
    assert status == "answered"
    assert letter == "B"


def test_extract_no_answer_when_pattern_absent():
    text = "I'm not sure about this one, there are several plausible options."
    status, letter = mmlu.extract_final_answer(text)
    assert status == "no_answer"
    assert letter is None


def test_extract_case_insensitive():
    text = "final answer: a"
    status, letter = mmlu.extract_final_answer(text)
    assert status == "answered"
    assert letter == "A"


def test_extract_no_answer_on_truncated_text_missing_pattern():
    # Simulates a generation cut off mid-reasoning before it ever reached
    # a FINAL ANSWER line.
    text = "Let's think step by step. First, we note that 7 + 5 is the sum of"
    status, letter = mmlu.extract_final_answer(text)
    assert status == "no_answer"
    assert letter is None


def test_evaluate_question_marks_truncated_even_if_answer_pattern_present(monkeypatch):
    # This is the exact bug scenario: finish_reason == "length" must win
    # over any extracted answer, even if a FINAL ANSWER: X happens to
    # appear somewhere in the truncated text.
    q = mmlu.Question(id="q1", category="test", question="2+2?", options=["3", "4", "5", "6"], answer="B")

    def fake_chat_completion(config, messages):
        return ChatResult(ok=True, content="FINAL ANSWER: B (but cut off here", finish_reason="length")

    monkeypatch.setattr(mmlu, "chat_completion", fake_chat_completion)

    result = mmlu.evaluate_question(ChatConfig(), q)
    assert result.status == "truncated"
    assert result.extracted_answer is None


def test_evaluate_question_correct_and_wrong(monkeypatch):
    q = mmlu.Question(id="q1", category="test", question="2+2?", options=["3", "4", "5", "6"], answer="B")

    def fake_correct(config, messages):
        return ChatResult(ok=True, content="reasoning...\nFINAL ANSWER: B", finish_reason="stop")

    monkeypatch.setattr(mmlu, "chat_completion", fake_correct)
    result = mmlu.evaluate_question(ChatConfig(), q)
    assert result.status == "correct"

    def fake_wrong(config, messages):
        return ChatResult(ok=True, content="reasoning...\nFINAL ANSWER: C", finish_reason="stop")

    monkeypatch.setattr(mmlu, "chat_completion", fake_wrong)
    result = mmlu.evaluate_question(ChatConfig(), q)
    assert result.status == "wrong"


def test_evaluate_question_error_on_request_failure(monkeypatch):
    q = mmlu.Question(id="q1", category="test", question="2+2?", options=["3", "4", "5", "6"], answer="B")

    def fake_error(config, messages):
        return ChatResult(ok=False, error="connection refused")

    monkeypatch.setattr(mmlu, "chat_completion", fake_error)
    result = mmlu.evaluate_question(ChatConfig(), q)
    assert result.status == "error"
    assert result.error == "connection refused"
