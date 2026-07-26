"""Tests for `localeval resume`: rerunning only the errored items from a
previous run and merging them back into that run directory in place.

"Errored" means a request failure - not truncated/wrong/no_answer/fail,
which are legitimate scoring outcomes and must never be silently retried
away (that would be the same class of hidden-failure bug this project
exists to catch).
"""

import argparse
import json
import pathlib

from localeval import __main__ as cli
from localeval import code, ifeval, mmlu
from localeval.client import ChatConfig, ChatResult


def _resume_args(run_dir, **overrides):
    defaults = dict(
        run_dir=str(run_dir), base_url=None, model=None, api_key=None,
        max_tokens=None, timeout=None, concurrency=None, retries=None,
        retry_backoff=None, verify_timeout=None, scratch_dir=None,
        system_prompt=None, prompt_file=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _write_run_dir(tmp_path, mode, cfg_extra, records):
    run_dir = tmp_path / "runs" / mode / "20260101T000000Z"
    run_dir.mkdir(parents=True)
    cfg = {"mode": mode, "base_url": "http://localhost:8080", "model": "test-model", "max_tokens": 4096, "timeout": 120, **cfg_extra}
    with open(run_dir / "config.json", "w") as f:
        json.dump(cfg, f)
    with open(run_dir / "results.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return run_dir


def _read_results(run_dir):
    with open(run_dir / "results.jsonl") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_resume_reruns_only_errored_mmlu_items(tmp_path, monkeypatch):
    questions_file = pathlib.Path("sample_data/mmlu_sample.json").resolve()
    run_dir = _write_run_dir(
        tmp_path,
        "mmlu",
        {"questions_file": str(questions_file)},
        [
            {"id": "q1", "category": "arithmetic", "status": "correct", "extracted_answer": "C", "correct_answer": "C", "finish_reason": "stop", "request": {}, "raw_response": {}, "response_text": "", "error": ""},
            {"id": "q2", "category": "arithmetic", "status": "error", "extracted_answer": None, "correct_answer": "B", "finish_reason": "", "request": {}, "raw_response": None, "response_text": "", "error": "request failed: boom"},
        ],
    )

    calls = []

    def fake_chat_completion(config, messages):
        calls.append(messages)
        return ChatResult(ok=True, content="FINAL ANSWER: B", finish_reason="stop", attempts=1)

    monkeypatch.setattr(mmlu, "chat_completion", fake_chat_completion)

    result = cli.resume_run(run_dir, ChatConfig(), concurrency=1)

    assert len(calls) == 1  # only the errored item was rerun, not q1
    assert result["resumed"] == 1
    assert result["still_errored"] == 0

    merged = _read_results(run_dir)
    by_id = {r["id"]: r for r in merged}
    assert by_id["q1"]["status"] == "correct"  # untouched
    assert by_id["q2"]["status"] == "correct"  # rerun and fixed
    assert [r["id"] for r in merged] == ["q1", "q2"]  # original order preserved

    with open(run_dir / "summary.json") as f:
        summary = json.load(f)
    assert summary["correct"] == 2
    assert summary["error"] == 0

    reports = list(run_dir.glob("*-report.md"))
    assert len(reports) == 1  # stale report replaced, not accumulated


def test_resume_is_noop_when_nothing_errored(tmp_path):
    questions_file = pathlib.Path("sample_data/mmlu_sample.json").resolve()
    records = [
        {"id": "q1", "category": "arithmetic", "status": "correct", "extracted_answer": "C", "correct_answer": "C", "finish_reason": "stop", "request": {}, "raw_response": {}, "response_text": "", "error": ""},
    ]
    run_dir = _write_run_dir(tmp_path, "mmlu", {"questions_file": str(questions_file)}, records)

    result = cli.resume_run(run_dir, ChatConfig(), concurrency=1)

    assert result["resumed"] == 0
    assert _read_results(run_dir) == records  # untouched
    assert not (run_dir / "summary.json").exists()  # never rewritten


def test_resume_reruns_only_errored_ifeval_case(tmp_path, monkeypatch):
    cases_file = pathlib.Path("sample_data/ifeval_sample.json").resolve()
    run_dir = _write_run_dir(
        tmp_path,
        "ifeval",
        {"cases_file": str(cases_file)},
        [
            {"id": "c1", "constraint_type": "exact_word_count", "status": "error", "error": "request failed: boom", "request": {}},
            {"id": "c2", "constraint_type": "must_not_include", "status": "pass", "finish_reason": "stop", "request": {}, "raw_response": {}, "response_text": "a feline pet"},
        ],
    )

    def fake_chat_completion(config, messages):
        return ChatResult(ok=True, content="one two three four five six seven eight nine ten", finish_reason="stop", attempts=1)

    monkeypatch.setattr(ifeval, "chat_completion", fake_chat_completion)

    result = cli.resume_run(run_dir, ChatConfig(), concurrency=1)

    assert result["resumed"] == 1
    merged = _read_results(run_dir)
    by_id = {r["id"]: r for r in merged}
    assert by_id["c1"]["status"] == "pass"
    assert by_id["c2"]["status"] == "pass"  # untouched


def test_resume_reruns_only_errored_code_task_by_name(tmp_path, monkeypatch):
    tasks_dir = pathlib.Path("sample_data/code_tasks").resolve()
    run_dir = _write_run_dir(
        tmp_path,
        "code",
        {"tasks_dir": str(tasks_dir), "verify_timeout": 10},
        [
            {"name": "reverse-string", "status": "error", "error": "request failed: boom", "request": {}},
        ],
    )

    def fake_chat_completion(config, messages):
        return ChatResult(ok=True, content="```python\ndef reverse_string(s):\n    return s[::-1]\n```", finish_reason="stop", attempts=1)

    monkeypatch.setattr(code, "chat_completion", fake_chat_completion)

    result = cli.resume_run(run_dir, ChatConfig(), concurrency=1, verify_timeout=10)

    assert result["resumed"] == 1
    merged = _read_results(run_dir)
    assert merged[0]["name"] == "reverse-string"
    assert merged[0]["status"] == "pass"


def test_cmd_resume_uses_persisted_system_prompt_and_api_key(tmp_path, monkeypatch):
    """`resume` must reuse the original run's --system-prompt/--api-key
    from config.json, not silently fall back to the per-mode default -
    both are only ever written to config.json, never passed on the CLI
    for `resume` unless explicitly overridden."""
    questions_file = pathlib.Path("sample_data/mmlu_sample.json").resolve()
    run_dir = _write_run_dir(
        tmp_path,
        "mmlu",
        {
            "questions_file": str(questions_file),
            "system_prompt": "You are a math wizard.",
            "api_key": "secret-key-123",
        },
        [
            {"id": "q1", "category": "arithmetic", "status": "error", "extracted_answer": None, "correct_answer": "B", "finish_reason": "", "request": {}, "raw_response": None, "response_text": "", "error": "request failed: boom"},
        ],
    )

    seen_configs = []

    def fake_chat_completion(config, messages):
        seen_configs.append(config)
        return ChatResult(ok=True, content="FINAL ANSWER: B", finish_reason="stop", attempts=1)

    monkeypatch.setattr(mmlu, "chat_completion", fake_chat_completion)

    cli.cmd_resume(_resume_args(run_dir))

    assert len(seen_configs) == 1
    assert seen_configs[0].system_prompt == "You are a math wizard."
    assert seen_configs[0].api_key == "secret-key-123"


def test_cmd_resume_cli_overrides_take_precedence_over_persisted_values(tmp_path, monkeypatch):
    questions_file = pathlib.Path("sample_data/mmlu_sample.json").resolve()
    run_dir = _write_run_dir(
        tmp_path,
        "mmlu",
        {"questions_file": str(questions_file), "system_prompt": "old prompt", "api_key": "old-key"},
        [
            {"id": "q1", "category": "arithmetic", "status": "error", "extracted_answer": None, "correct_answer": "B", "finish_reason": "", "request": {}, "raw_response": None, "response_text": "", "error": "request failed: boom"},
        ],
    )

    seen_configs = []

    def fake_chat_completion(config, messages):
        seen_configs.append(config)
        return ChatResult(ok=True, content="FINAL ANSWER: B", finish_reason="stop", attempts=1)

    monkeypatch.setattr(mmlu, "chat_completion", fake_chat_completion)

    cli.cmd_resume(_resume_args(run_dir, system_prompt="new prompt", api_key="new-key"))

    assert seen_configs[0].system_prompt == "new prompt"
    assert seen_configs[0].api_key == "new-key"


def test_resume_uses_persisted_scratch_dir_for_code_mode(tmp_path, monkeypatch):
    tasks_dir = pathlib.Path("sample_data/code_tasks").resolve()
    custom_scratch = tmp_path / "my-custom-scratch"
    run_dir = _write_run_dir(
        tmp_path,
        "code",
        {"tasks_dir": str(tasks_dir), "verify_timeout": 10, "scratch_dir": str(custom_scratch)},
        [
            {"name": "reverse-string", "status": "error", "error": "request failed: boom", "request": {}},
        ],
    )

    def fake_chat_completion(config, messages):
        return ChatResult(ok=True, content="```python\ndef reverse_string(s):\n    return s[::-1]\n```", finish_reason="stop", attempts=1)

    monkeypatch.setattr(code, "chat_completion", fake_chat_completion)

    result = cli.resume_run(run_dir, ChatConfig(), concurrency=1, verify_timeout=10)

    assert result["resumed"] == 1
    assert (custom_scratch / "reverse-string" / "solution.py").exists()
