"""MMLU-style multiple-choice benchmark mode.

Question bank format: a JSON file containing a list of objects:

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

`options` is a 4-element list corresponding to A, B, C, D. `answer` is the
correct letter.

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
import re
from dataclasses import dataclass, field

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


def run(config: ChatConfig, questions: list, concurrency: int, results_writer, limit: int = None) -> dict:
    if limit:
        questions = questions[:limit]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(evaluate_question, config, q): q for q in questions}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            results.append(r)
            results_writer.write(
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

    correct = sum(1 for r in results if r.status == "correct")
    wrong = sum(1 for r in results if r.status == "wrong")
    truncated = sum(1 for r in results if r.status == "truncated")
    no_answer = sum(1 for r in results if r.status == "no_answer")
    errors = sum(1 for r in results if r.status == "error")

    denominator = correct + wrong
    accuracy = (correct / denominator * 100) if denominator else 0.0

    by_category = {}
    for r in results:
        cat = by_category.setdefault(r.category, {"correct": 0, "wrong": 0, "truncated": 0, "no_answer": 0, "error": 0})
        cat[r.status] += 1

    category_summary = {}
    for cat, counts in by_category.items():
        denom = counts["correct"] + counts["wrong"]
        acc = (counts["correct"] / denom * 100) if denom else 0.0
        category_summary[cat] = {"accuracy_pct": round(acc, 1), **counts}

    return {
        "total": len(results),
        "correct": correct,
        "wrong": wrong,
        "truncated": truncated,
        "no_answer": no_answer,
        "error": errors,
        "accuracy_pct": round(accuracy, 1),
        "by_category": category_summary,
    }
