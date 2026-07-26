"""MMLU-style multiple-choice benchmark mode.

Two question bank formats are supported, dispatched on file extension:

1. `.json` - a JSON file containing a list of objects:

    [
      {
        "id": "q1",
        "category": "abstract_algebra",
        "question": "...",
        "options": ["...", "...", "...", "..."],
        "answer": "B"
      },
      ...
    ]

   `options` is a 4-element list corresponding to A, B, C, D. `answer` is
   the correct letter.

2. `.md` / `.txt` - a plain-text bank with a `## QUESTIONS` section
   containing `### Category Name` headings followed by numbered lines:

    1. What is 15% of 200?  A. 20  B. 30  C. 25  D. 40

   and a separate `## ANSWER KEY` section with space-separated
   `N-LETTER` tokens (e.g. `1-C 2-B 3-A`), so the answer key can be kept
   out of what gets pasted to a model under test.

The model is asked to think it through and finish with a line reading
"FINAL ANSWER: X". The response is only ever trusted for its LAST such
match, scanning from the end, and finish_reason == "length" always wins
and marks the question TRUNCATED regardless of what text is present -
this is the exact failure mode that produced a false 22.8% MMLU score in
a previous harness.
"""

from __future__ import annotations

import concurrent.futures
import json
import pathlib
import re
from dataclasses import dataclass, field

from . import display, reporting
from .client import ChatConfig, chat_completion

FINAL_ANSWER_RE = re.compile(r"FINAL ANSWER:\s*([A-D])\b", re.IGNORECASE)

LETTERS = ["A", "B", "C", "D"]

SYSTEM_PROMPT = (
    "You are answering a multiple-choice question. Think it through, then "
    "end your response on its own final line, exactly in this format:\n"
    "FINAL ANSWER: X\n"
    "where X is A, B, C, or D."
)


@dataclass
class Question:
    id: str
    category: str
    question: str
    options: list
    answer: str


def load_questions(path: str) -> list:
    if pathlib.Path(path).suffix.lower() == ".json":
        return _load_json_bank(path)
    return _load_markdown_bank(path)


def _load_json_bank(path: str) -> list:
    with open(path) as f:
        raw = json.load(f)
    questions = []
    for item in raw:
        questions.append(
            Question(
                id=str(item["id"]),
                category=item.get("category", "uncategorized"),
                question=item["question"],
                options=item["options"],
                answer=item["answer"].strip().upper(),
            )
        )
    return questions


_QUESTIONS_SECTION_RE = re.compile(r"##\s*QUESTIONS.*?\n(.*?)(?=\n##\s*ANSWER KEY|\Z)", re.DOTALL | re.IGNORECASE)
_ANSWER_KEY_SECTION_RE = re.compile(r"##\s*ANSWER KEY.*?\n(.*)", re.DOTALL | re.IGNORECASE)
_ANSWER_ENTRY_RE = re.compile(r"(\d+)-([A-D])")
_CATEGORY_HEADING_RE = re.compile(r"^###\s+(.*)$")
_QUESTION_LINE_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_OPTION_SPLIT_RE = re.compile(r"\s{2,}(?=[A-D]\.\s)")
_OPTION_RE = re.compile(r"^[A-D]\.\s*(.*)$")


def _load_markdown_bank(path: str) -> list:
    text = pathlib.Path(path).read_text()

    q_match = _QUESTIONS_SECTION_RE.search(text)
    if not q_match:
        raise ValueError(f"No '## QUESTIONS' section found in {path}")

    key_match = _ANSWER_KEY_SECTION_RE.search(text)
    if not key_match:
        raise ValueError(f"No '## ANSWER KEY' section found in {path}")
    answer_key = {int(n): letter.upper() for n, letter in _ANSWER_ENTRY_RE.findall(key_match.group(1))}

    category = "uncategorized"
    questions = []
    for line in q_match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue

        heading_match = _CATEGORY_HEADING_RE.match(line)
        if heading_match:
            category = heading_match.group(1).strip()
            continue

        q_line_match = _QUESTION_LINE_RE.match(line)
        if not q_line_match:
            continue

        num = int(q_line_match.group(1))
        parts = _OPTION_SPLIT_RE.split(q_line_match.group(2))
        if len(parts) != 5:
            raise ValueError(f"Expected 4 options for question {num} in {path}, got {len(parts) - 1}: {line!r}")

        question_text, *option_parts = parts
        options = []
        for opt in option_parts:
            opt_match = _OPTION_RE.match(opt)
            if not opt_match:
                raise ValueError(f"Malformed option for question {num} in {path}: {opt!r}")
            options.append(opt_match.group(1).strip())

        if num not in answer_key:
            raise ValueError(f"No answer key entry for question {num} in {path}")

        questions.append(
            Question(
                id=f"q{num}",
                category=category,
                question=question_text.strip(),
                options=options,
                answer=answer_key[num],
            )
        )

    return questions


def build_user_prompt(q: Question) -> str:
    lines = [q.question, ""]
    for letter, option in zip(LETTERS, q.options):
        lines.append(f"{letter}. {option}")
    return "\n".join(lines)


def extract_final_answer(text: str) -> tuple:
    """Return (status, letter). status is one of: "answered", "no_answer".

    Always takes the LAST "FINAL ANSWER: X" match in the text, scanning
    from the end - never the first letter-like token anywhere in the
    response (that was the bug: it matched restated multiple-choice
    options being echoed back by the model).
    """
    matches = FINAL_ANSWER_RE.findall(text)
    if not matches:
        return "no_answer", None
    return "answered", matches[-1].upper()


@dataclass
class QuestionResult:
    id: str
    category: str
    status: str  # correct | wrong | truncated | no_answer | error
    extracted_answer: str = None
    correct_answer: str = ""
    finish_reason: str = ""
    request: dict = field(default_factory=dict)
    raw_response: dict = None
    response_text: str = ""
    error: str = ""


def evaluate_question(config: ChatConfig, q: Question) -> QuestionResult:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(q)},
    ]
    request = {"messages": messages, "max_tokens": config.max_tokens, "model": config.model}

    result = chat_completion(config, messages)
    request["attempts"] = result.attempts

    if not result.ok:
        return QuestionResult(
            id=q.id,
            category=q.category,
            status="error",
            correct_answer=q.answer,
            request=request,
            error=result.error,
        )

    if result.finish_reason == "length":
        return QuestionResult(
            id=q.id,
            category=q.category,
            status="truncated",
            correct_answer=q.answer,
            finish_reason=result.finish_reason,
            request=request,
            raw_response=result.raw_response,
            response_text=result.content,
        )

    status, letter = extract_final_answer(result.content)
    if status == "no_answer":
        final_status = "no_answer"
    else:
        final_status = "correct" if letter == q.answer else "wrong"

    return QuestionResult(
        id=q.id,
        category=q.category,
        status=final_status,
        extracted_answer=letter,
        correct_answer=q.answer,
        finish_reason=result.finish_reason,
        request=request,
        raw_response=result.raw_response,
        response_text=result.content,
    )


def run(config: ChatConfig, questions: list, concurrency: int, results_writer, limit: int = None, show_progress: bool = True) -> dict:
    questions = reporting.apply_limit(questions, limit)

    records = []
    progress = display.make_progress("MMLU") if show_progress else None
    task_id = progress.add_task("MMLU", total=len(questions)) if progress else None
    if progress:
        progress.start()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {pool.submit(evaluate_question, config, q): q for q in questions}
            for future in concurrent.futures.as_completed(futures):
                r = future.result()
                records.append(
                    {
                        "id": r.id,
                        "category": r.category,
                        "status": r.status,
                        "extracted_answer": r.extracted_answer,
                        "correct_answer": r.correct_answer,
                        "finish_reason": r.finish_reason,
                        "request": r.request,
                        "raw_response": r.raw_response,
                        "response_text": r.response_text,
                        "error": r.error,
                    }
                )
                results_writer.write(records[-1])
                if progress:
                    correct_so_far = sum(1 for x in records if x["status"] == "correct")
                    wrong_so_far = sum(1 for x in records if x["status"] == "wrong")
                    progress.update(
                        task_id,
                        advance=1,
                        description=f"MMLU  ✅ {correct_so_far}  ❌ {wrong_so_far}",
                    )
    finally:
        if progress:
            progress.stop()

    return summarize(records), records


def summarize(records: list) -> dict:
    correct = sum(1 for r in records if r["status"] == "correct")
    wrong = sum(1 for r in records if r["status"] == "wrong")
    truncated = sum(1 for r in records if r["status"] == "truncated")
    no_answer = sum(1 for r in records if r["status"] == "no_answer")
    errors = sum(1 for r in records if r["status"] == "error")

    denominator = correct + wrong
    accuracy = (correct / denominator * 100) if denominator else 0.0

    by_category = {}
    for r in records:
        cat = by_category.setdefault(r["category"], {"correct": 0, "wrong": 0, "truncated": 0, "no_answer": 0, "error": 0})
        cat[r["status"]] += 1

    category_summary = {}
    for cat, counts in by_category.items():
        denom = counts["correct"] + counts["wrong"]
        acc = (counts["correct"] / denom * 100) if denom else 0.0
        category_summary[cat] = {"accuracy_pct": round(acc, 1), **counts}

    return {
        "total": len(records),
        "correct": correct,
        "wrong": wrong,
        "truncated": truncated,
        "no_answer": no_answer,
        "error": errors,
        "accuracy_pct": round(accuracy, 1),
        "by_category": category_summary,
    }
