"""Tests for --dry-run validation that catches malformed input before
kicking off a long benchmark run."""

import pathlib
import json

from localeval import mmlu, code, ifeval


def test_load_valid_json_mmlu_bank(tmp_path):
    """A well-formed JSON bank loads without errors."""
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps([
        {"id": "q1", "category": "math", "question": "2+2?", "options": ["3", "4", "5", "6"], "answer": "B"},
        {"id": "q2", "category": "history", "question": "Who?", "options": ["A", "B", "C", "D"], "answer": "A"},
    ]))
    questions = mmlu.load_questions(str(bank))
    assert len(questions) == 2
    assert questions[0].id == "q1"


def test_load_valid_markdown_mmlu_bank(tmp_path):
    """A well-formed markdown bank loads without errors."""
    bank = tmp_path / "bank.md"
    bank.write_text("""## QUESTIONS

### Math
1. What is 2+2?  A. 3  B. 4  C. 5  D. 6
### Science
2. H2O is?  A. Water  B. Fire  C. Earth  D. Air

## ANSWER KEY
1-B 2-A
""")
    questions = mmlu.load_questions(str(bank))
    assert len(questions) == 2


def test_load_invalid_markdown_mmlu_bank_missing_options(tmp_path):
    """A malformed markdown bank raises a clear error."""
    bank = tmp_path / "bank.md"
    bank.write_text("""## QUESTIONS

### Math
1. What is 2+2?  A. 3  B. 4

## ANSWER KEY
1-B
""")  # Only 2 options, not 4
    try:
        mmlu.load_questions(str(bank))
        assert False, "should have raised"
    except ValueError as e:
        assert "Expected 4 options" in str(e)


def test_load_valid_code_tasks(tmp_path):
    """A well-formed task directory loads without errors."""
    task_dir = tmp_path / "my-task"
    task_dir.mkdir()
    (task_dir / "task.md").write_text("Write a function that reverses a string.")
    (task_dir / "verify.sh").write_text("#!/bin/bash\nexit 0")
    (task_dir / "verify.sh").chmod(0o755)

    tasks = code.load_tasks(str(tmp_path))
    assert len(tasks) == 1
    assert tasks[0]["name"] == "my-task"


def test_load_code_tasks_skips_missing_verify(tmp_path):
    """A task dir without verify.sh is skipped (not an error)."""
    task_dir = tmp_path / "no-verify"
    task_dir.mkdir()
    (task_dir / "task.md").write_text("Some task")

    tasks = code.load_tasks(str(tmp_path))
    assert len(tasks) == 0


def test_load_valid_ifeval_cases(tmp_path):
    """A well-formed IFEval case file loads without errors."""
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(json.dumps([
        {"id": "c1", "prompt": "Say hello in exactly 5 words.", "constraint_type": "exact_word_count", "constraint_params": {"n": 5}},
        {"id": "c2", "prompt": "Reply in JSON.", "constraint_type": "valid_json", "constraint_params": {}},
    ]))
    cases = ifeval.load_cases(str(cases_file))
    assert len(cases) == 2


def test_load_ifeval_cases_unknown_constraint_still_loads(tmp_path):
    """Unknown constraint types still load - they get flagged at eval time."""
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(json.dumps([
        {"id": "c1", "prompt": "...", "constraint_type": "nonexistent_checker", "constraint_params": {}},
    ]))
    cases = ifeval.load_cases(str(cases_file))
    assert len(cases) == 1
    assert cases[0].constraint_type == "nonexistent_checker"


def test_load_invalid_json_raises(tmp_path):
    """Malformed JSON raises an error."""
    bank = tmp_path / "bank.json"
    bank.write_text("{not valid json")
    try:
        mmlu.load_questions(str(bank))
        assert False, "should have raised"
    except json.JSONDecodeError:
        pass


def test_dry_run_does_not_send_requests(monkeypatch, tmp_path):
    """--dry-run loads and validates the bank but never calls chat_completion."""
    from localeval.__main__ import main

    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps([
        {"id": "q1", "category": "test", "question": "2+2?", "options": ["3", "4", "5", "6"], "answer": "B"},
    ]))

    called = []

    def fake_chat(*args, **kwargs):
        called.append(1)

    monkeypatch.setattr("localeval.client.chat_completion", fake_chat)

    # --dry-run should succeed without calling the server
    exit_code = main(["mmlu", "--questions", str(bank), "--dry-run"])
    assert exit_code == 0
    assert len(called) == 0


def test_dry_run_reports_count(tmp_path, capsys):
    """--dry-run prints the number of items loaded."""
    from localeval.__main__ import main

    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps([
        {"id": "q1", "category": "test", "question": "2+2?", "options": ["3", "4", "5", "6"], "answer": "B"},
        {"id": "q2", "category": "test", "question": "3+3?", "options": ["5", "6", "7", "8"], "answer": "B"},
    ]))

    main(["mmlu", "--questions", str(bank), "--dry-run"])
    captured = capsys.readouterr()
    assert "2 questions" in captured.out


def test_dry_run_reports_malformed_input(tmp_path, capsys):
    """--dry-run catches malformed input and exits non-zero."""
    import pytest
    from localeval.__main__ import main

    bank = tmp_path / "bank.md"
    bank.write_text("""## QUESTIONS

1. What is 2+2?  A. 3  B. 4

## ANSWER KEY
1-B
""")

    with pytest.raises(SystemExit) as exc_info:
        main(["mmlu", "--questions", str(bank), "--dry-run"])
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Expected 4 options" in captured.err
