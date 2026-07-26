"""Tests for the plain-text MMLU bank parser (category headings + numbered
question lines + a separate answer key section)."""

import pathlib

import pytest

from localeval import mmlu

SAMPLE = """\
# Test Bank

## QUESTIONS (paste this section only - no answers included)

### Elementary Mathematics
1. What is 15% of 200?  A. 20  B. 30  C. 25  D. 40
2. What is the least common multiple of 4 and 6?  A. 10  B. 12  C. 24  D. 8

### High School Mathematics
3. Solve for x: 2x - 5 = 11  A. 3  B. 8  C. 6  D. 16

---

## ANSWER KEY (do not paste to the model - for scoring only)

1-C 2-B
3-B
"""


def test_parses_all_questions_with_categories_and_answers(tmp_path):
    path = tmp_path / "bank.md"
    path.write_text(SAMPLE)

    questions = mmlu.load_questions(str(path))

    assert len(questions) == 3
    assert questions[0].id == "q1"
    assert questions[0].category == "Elementary Mathematics"
    assert questions[0].question == "What is 15% of 200?"
    assert questions[0].options == ["20", "30", "25", "40"]
    assert questions[0].answer == "C"

    assert questions[1].category == "Elementary Mathematics"
    assert questions[1].answer == "B"

    assert questions[2].category == "High School Mathematics"
    assert questions[2].answer == "B"


def test_missing_answer_key_entry_raises(tmp_path):
    broken = SAMPLE.replace("1-C 2-B\n3-B\n", "1-C 2-B\n")
    path = tmp_path / "bank.md"
    path.write_text(broken)

    with pytest.raises(ValueError, match="No answer key entry for question 3"):
        mmlu.load_questions(str(path))


def test_malformed_question_line_raises(tmp_path):
    broken = SAMPLE.replace(
        "1. What is 15% of 200?  A. 20  B. 30  C. 25  D. 40",
        "1. What is 15% of 200?  A. 20  B. 30  C. 25",
    )
    path = tmp_path / "bank.md"
    path.write_text(broken)

    with pytest.raises(ValueError, match="Expected 4 options for question 1"):
        mmlu.load_questions(str(path))


def test_real_200_question_bank_parses_completely_and_matches_answer_key():
    bank_path = pathlib.Path(__file__).parent.parent / "sample_data" / "mmlu-test-bank-200.md"
    if not bank_path.exists():
        pytest.skip("mmlu-test-bank-200.md not present")

    text = bank_path.read_text()
    expected_answers = {int(n): letter.upper() for n, letter in mmlu._ANSWER_ENTRY_RE.findall(text.split("ANSWER KEY")[1])}

    questions = mmlu.load_questions(str(bank_path))

    assert len(questions) == 200
    assert len(expected_answers) == 200

    seen_ids = {q.id for q in questions}
    assert seen_ids == {f"q{n}" for n in range(1, 201)}

    for q in questions:
        num = int(q.id[1:])
        assert q.answer == expected_answers[num], f"question {num}: parsed answer {q.answer} != answer key {expected_answers[num]}"
        assert len(q.options) == 4
        assert q.category != "uncategorized"
