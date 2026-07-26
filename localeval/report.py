"""Human-readable per-run debug report.

Written alongside config.json/results.jsonl/summary.json as
<date>-<model>-<uuid>-report.md. results.jsonl stays the source of full
raw request/response data - this file is a readable index into it,
surfacing anything that needs attention (wrong/truncated/no_answer/error/
fail/timeout) up front instead of making you grep for it.
"""

from __future__ import annotations

import json
import pathlib
import re
import uuid
from datetime import datetime, timezone


def _slug(text: str) -> str:
    text = (text or "").strip()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    return slug or "unknown-model"


def report_filename(model: str) -> str:
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{date}-{_slug(model)}-{uuid.uuid4()}-report.md"


def _excerpt(text: str, n: int = 400) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n] + " ...[truncated in report, see results.jsonl for full text]"


def _mmlu_sections(results: list) -> list:
    attention = [r for r in results if r["status"] != "correct"]
    lines = ["## Items needing attention", ""]
    if not attention:
        lines.append("None - every question was answered and correct.")
    for r in attention:
        lines.append(f"### {r['id']} ({r['category']}) - {r['status'].upper()}")
        lines.append(f"- expected: `{r['correct_answer']}`, extracted: `{r.get('extracted_answer')}`")
        lines.append(f"- finish_reason: `{r.get('finish_reason')}`")
        if r.get("error"):
            lines.append(f"- error: {r['error']}")
        lines.append(f"- response excerpt: {_excerpt(r.get('response_text', ''))}")
        lines.append("")

    lines.append("## All items")
    lines.append("")
    lines.append("| id | category | status | expected | extracted |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        lines.append(f"| {r['id']} | {r['category']} | {r['status']} | {r['correct_answer']} | {r.get('extracted_answer')} |")
    return lines


def _code_sections(results: list) -> list:
    attention = [r for r in results if r["status"] != "pass"]
    lines = ["## Items needing attention", ""]
    if not attention:
        lines.append("None - every task passed verification.")
    for r in attention:
        lines.append(f"### {r['name']} - {r['status'].upper()}")
        if r.get("error"):
            lines.append(f"- error: {r['error']}")
        if "verify_returncode" in r:
            lines.append(f"- verify_returncode: `{r['verify_returncode']}`")
            lines.append(f"- verify_stdout: {_excerpt(r.get('verify_stdout', ''))}")
            lines.append(f"- verify_stderr: {_excerpt(r.get('verify_stderr', ''))}")
        lines.append(f"- response excerpt: {_excerpt(r.get('response_text', ''))}")
        lines.append("")

    lines.append("## All items")
    lines.append("")
    lines.append("| name | status |")
    lines.append("|---|---|")
    for r in results:
        lines.append(f"| {r['name']} | {r['status']} |")
    return lines


def _ifeval_sections(results: list) -> list:
    attention = [r for r in results if r["status"] != "pass"]
    lines = ["## Items needing attention", ""]
    if not attention:
        lines.append("None - every case passed.")
    for r in attention:
        lines.append(f"### {r['id']} ({r['constraint_type']}) - {r['status'].upper()}")
        if r.get("error"):
            lines.append(f"- error: {r['error']}")
        lines.append(f"- response excerpt: {_excerpt(r.get('response_text', ''))}")
        lines.append("")

    lines.append("## All items")
    lines.append("")
    lines.append("| id | constraint_type | status |")
    lines.append("|---|---|---|")
    for r in results:
        lines.append(f"| {r['id']} | {r['constraint_type']} | {r['status']} |")
    return lines


_MODE_SECTIONS = {
    "mmlu": _mmlu_sections,
    "code": _code_sections,
    "ifeval": _ifeval_sections,
}


def write_report(run_dir: pathlib.Path, mode: str, config: dict, summary: dict, results: list) -> pathlib.Path:
    model = config.get("model") or "unknown-model"
    path = run_dir / report_filename(model)

    lines = [
        f"# localeval {mode} report",
        "",
        f"- generated: {datetime.now(timezone.utc).isoformat()}",
        f"- model: {model}",
        f"- base_url: {config.get('base_url')}",
        f"- run_dir: `{run_dir}`",
        "",
        "## Config",
        "",
        "```json",
        json.dumps(config, indent=2, default=str),
        "```",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2, default=str),
        "```",
        "",
    ]

    section_fn = _MODE_SECTIONS.get(mode)
    if section_fn:
        lines.extend(section_fn(results))
        lines.append("")

    lines.append(f"Full raw request/response for every item: `results.jsonl` in this directory (grep by id).")

    path.write_text("\n".join(lines) + "\n")
    return path
