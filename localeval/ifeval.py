"""IFEval-light mode: hand-rolled, objectively-checkable instruction-following
constraints. Not a reimplementation of Google's IFEval verifier suite - just
a small set of pure functions, each constraint_type -> pass/fail.

Case format: a JSON file containing a list of objects:

    [
      {
        "id": "c1",
        "prompt": "Describe your favorite season in exactly 20 words.",
        "constraint_type": "exact_word_count",
        "constraint_params": {"n": 20}
      },
      ...
    ]

See README.md for the full list of constraint_type values and the params
each one expects.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import display, reporting
from .client import ChatConfig, chat_completion


def _words(text: str) -> list:
    return text.split()


def _sentences(text: str) -> list:
    parts = re.split(r"[.!?]+", text)
    return [p.strip() for p in parts if p.strip()]


def _paragraphs(text: str) -> list:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _strip_code_fence(text: str) -> str:
    match = re.search(r"```[a-zA-Z0-9_]*\n(.*?)```", text, re.DOTALL)
    return match.group(1) if match else text


def check_exact_word_count(text, params):
    return len(_words(text)) == params["n"]


def check_min_word_count(text, params):
    return len(_words(text)) >= params["n"]


def check_max_word_count(text, params):
    return len(_words(text)) <= params["n"]


def check_must_include(text, params):
    return params["word"].lower() in text.lower()


def check_must_not_include(text, params):
    return params["word"].lower() not in text.lower()


def check_must_include_all(text, params):
    lowered = text.lower()
    return all(w.lower() in lowered for w in params["words"])


def check_must_not_include_any(text, params):
    lowered = text.lower()
    return all(w.lower() not in lowered for w in params["words"])


def check_valid_json(text, params):
    try:
        json.loads(_strip_code_fence(text).strip())
        return True
    except (ValueError, TypeError):
        return False


def check_exact_bullet_count(text, params):
    bullets = [ln for ln in text.splitlines() if ln.strip().startswith(("-", "*"))]
    return len(bullets) == params["n"]


def check_forbidden_letter(text, params):
    return params["letter"].lower() not in text.lower()


def check_all_lowercase(text, params):
    return text == text.lower()


def check_all_uppercase(text, params):
    return text == text.upper()


def check_starts_with(text, params):
    return text.strip().startswith(params["prefix"])


def check_ends_with(text, params):
    return text.strip().endswith(params["suffix"])


def check_exact_sentence_count(text, params):
    return len(_sentences(text)) == params["n"]


def check_no_commas(text, params):
    return "," not in text


def check_contains_number(text, params):
    return bool(re.search(r"\d", text))


def check_exact_paragraph_count(text, params):
    return len(_paragraphs(text)) == params["n"]


CONSTRAINT_CHECKERS = {
    "exact_word_count": check_exact_word_count,
    "min_word_count": check_min_word_count,
    "max_word_count": check_max_word_count,
    "must_include": check_must_include,
    "must_not_include": check_must_not_include,
    "must_include_all": check_must_include_all,
    "must_not_include_any": check_must_not_include_any,
    "valid_json": check_valid_json,
    "exact_bullet_count": check_exact_bullet_count,
    "forbidden_letter": check_forbidden_letter,
    "all_lowercase": check_all_lowercase,
    "all_uppercase": check_all_uppercase,
    "starts_with": check_starts_with,
    "ends_with": check_ends_with,
    "exact_sentence_count": check_exact_sentence_count,
    "no_commas": check_no_commas,
    "contains_number": check_contains_number,
    "exact_paragraph_count": check_exact_paragraph_count,
}


@dataclass
class Case:
    id: str
    prompt: str
    constraint_type: str
    constraint_params: dict = field(default_factory=dict)


def load_cases(path: str) -> list:
    with open(path) as f:
        raw = json.load(f)
    cases = []
    for item in raw:
        cases.append(
            Case(
                id=str(item["id"]),
                prompt=item["prompt"],
                constraint_type=item["constraint_type"],
                constraint_params=item.get("constraint_params", {}),
            )
        )
    return cases


def evaluate_case(config: ChatConfig, case: Case) -> dict:
    messages = [{"role": "user", "content": case.prompt}]
    request = {"messages": messages, "max_tokens": config.max_tokens, "model": config.model}

    result = chat_completion(config, messages)
    request["attempts"] = result.attempts
    if not result.ok:
        return {
            "id": case.id,
            "constraint_type": case.constraint_type,
            "status": "error",
            "error": result.error,
            "request": request,
        }

    if result.finish_reason == "length":
        # A cut-off response must never be checked against a constraint:
        # it can spuriously pass some checks (e.g. max_word_count,
        # no_commas, forbidden_letter are all easier to satisfy with
        # less text) and spuriously fail others (valid_json,
        # exact_word_count) - neither outcome reflects whether the model
        # would have satisfied the constraint if it had finished.
        return {
            "id": case.id,
            "constraint_type": case.constraint_type,
            "status": "truncated",
            "finish_reason": result.finish_reason,
            "request": request,
            "raw_response": result.raw_response,
            "response_text": result.content,
            "ttft_ms": result.ttft_ms,
            "total_tokens": result.total_tokens,
            "tokens_per_second": result.tokens_per_second,
        }

    checker = CONSTRAINT_CHECKERS.get(case.constraint_type)
    if checker is None:
        return {
            "id": case.id,
            "constraint_type": case.constraint_type,
            "status": "unknown_constraint",
            "request": request,
            "raw_response": result.raw_response,
            "response_text": result.content,
            "ttft_ms": result.ttft_ms,
            "total_tokens": result.total_tokens,
            "tokens_per_second": result.tokens_per_second,
        }

    try:
        passed = checker(result.content, case.constraint_params)
    except (KeyError, TypeError) as exc:
        return {
            "id": case.id,
            "constraint_type": case.constraint_type,
            "status": "checker_error",
            "error": str(exc),
            "request": request,
            "raw_response": result.raw_response,
            "response_text": result.content,
            "ttft_ms": result.ttft_ms,
            "total_tokens": result.total_tokens,
            "tokens_per_second": result.tokens_per_second,
        }

    return {
        "id": case.id,
        "constraint_type": case.constraint_type,
        "status": "pass" if passed else "fail",
        "finish_reason": result.finish_reason,
        "request": request,
        "raw_response": result.raw_response,
        "response_text": result.content,
        "ttft_ms": result.ttft_ms,
        "total_tokens": result.total_tokens,
        "tokens_per_second": result.tokens_per_second,
    }


def run(config: ChatConfig, cases: list, results_writer, limit: int = None, show_progress: bool = True) -> dict:
    cases = reporting.apply_limit(cases, limit)

    results = []
    progress = display.make_progress("IFEval-light") if show_progress else None
    task_id = progress.add_task("IFEval-light", total=len(cases)) if progress else None
    if progress:
        progress.start()

    try:
        for case in cases:
            r = evaluate_case(config, case)
            results.append(r)
            results_writer.write(r)
            if progress:
                passed_so_far = sum(1 for x in results if x["status"] == "pass")
                failed_so_far = sum(1 for x in results if x["status"] == "fail")
                progress.update(
                    task_id,
                    advance=1,
                    description=f"IFEval-light  ✅ {passed_so_far}  ❌ {failed_so_far}",
                )
    finally:
        if progress:
            progress.stop()

    return summarize(results), results


def summarize(results: list) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    # "error" is a request failure - we have zero information about whether
    # the model would have passed or failed. "other" is a case-authoring
    # problem (bad constraint_type or bad constraint_params), not a model
    # or request issue. Keeping these separate matters: silently folding
    # request errors into a vague "other" bucket is exactly the kind of
    # masking that produced a false 22.8% MMLU score in a previous harness.
    errors = sum(1 for r in results if r["status"] == "error")
    truncated = sum(1 for r in results if r["status"] == "truncated")
    other = sum(1 for r in results if r["status"] in ("unknown_constraint", "checker_error"))

    denom = passed + failed
    overall_pct = (passed / denom * 100) if denom else 0.0

    by_constraint = {}
    for r in results:
        ct = by_constraint.setdefault(r["constraint_type"], {"pass": 0, "fail": 0, "error": 0, "truncated": 0, "other": 0})
        if r["status"] == "pass":
            ct["pass"] += 1
        elif r["status"] == "fail":
            ct["fail"] += 1
        elif r["status"] == "error":
            ct["error"] += 1
        elif r["status"] == "truncated":
            ct["truncated"] += 1
        else:
            ct["other"] += 1

    per_constraint_summary = {}
    for ct, counts in by_constraint.items():
        d = counts["pass"] + counts["fail"]
        pct = (counts["pass"] / d * 100) if d else 0.0
        per_constraint_summary[ct] = {"pass_rate_pct": round(pct, 1), **counts}

    return {
        "total": total,
        "pass": passed,
        "fail": failed,
        "error": errors,
        "truncated": truncated,
        "other": other,
        "overall_pass_rate_pct": round(overall_pct, 1),
        "by_constraint": per_constraint_summary,
        "latency": reporting.latency_stats(results),
    }
