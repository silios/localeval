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

from . import display
from .reporting import score_fields


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


def _benchmark_summary_section(mode: str, model: str, summary: dict, elapsed_s: float) -> list:
    """The same score/rating/badges/coverage content shown in the
    terminal's final panel (see localeval.display.print_final_panel),
    rendered as markdown so it's captured in the report file too - not
    just the raw JSON summary dump.
    """
    fields = score_fields(mode, summary)
    earned, total, run_total, counts = fields["earned"], fields["total"], fields["run_total"], fields["counts"]
    pct = (earned / total * 100) if total else 0.0
    errored = counts.get("error", 0)

    lines = [
        "## Benchmark Summary",
        "",
        f"- **Score:** {earned} / {total} (of items that produced a scorable answer)",
        f"- **Rating:** {display.rating_for(pct)}",
    ]

    badges = []
    if counts.get("pass"):
        badges.append(f"✅ {counts['pass']} passed")
    if counts.get("partial"):
        badges.append(f"⚠ {counts['partial']} partial")
    if counts.get("fail"):
        badges.append(f"❌ {counts['fail']} failed")
    if errored:
        badges.append(f"⛔ {errored} errored")
    if badges:
        lines.append(f"- **Results:** {'   '.join(badges)}")

    if run_total != total:
        scored_or_partial = total + counts.get("partial", 0)
        lines.append(f"- **Coverage:** {scored_or_partial}/{run_total} items produced any response - {errored} never got one.")

    latency = fields.get("latency") or {}
    if latency.get("timed_items"):
        timed = latency["timed_items"]
        lines.append(f"- **Latency** (p50 / p95, {timed} items)")
        lines.append(f"  - TTFT: {latency['ttft_p50_ms']:.0f}ms / {latency['ttft_p95_ms']:.0f}ms")
        lines.append(f"  - tokens/sec: {latency['tps_p50']:.1f} / {latency['tps_p95']:.1f}")

    lines.append(f"- **Completed in:** {elapsed_s:.1f}s")
    lines.append("")
    return lines


def write_report(run_dir: pathlib.Path, mode: str, config: dict, summary: dict, results: list, elapsed_s: float = 0.0) -> pathlib.Path:
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
    ]
    lines.extend(_benchmark_summary_section(mode, model, summary, elapsed_s))
    lines.extend(
        [
            "## Config",
            "",
            "```json",
            json.dumps(config, indent=2, default=str),
            "```",
            "",
            "## Summary (raw)",
            "",
            "```json",
            json.dumps(summary, indent=2, default=str),
            "```",
            "",
        ]
    )

    section_fn = _MODE_SECTIONS.get(mode)
    if section_fn:
        lines.extend(section_fn(results))
        lines.append("")

    lines.append(f"Full raw request/response for every item: `results.jsonl` in this directory (grep by id).")

    path.write_text("\n".join(lines) + "\n")
    return path


def write_bench_report(run_dir: pathlib.Path, config: dict, summary: dict, results: list, elapsed_s: float = 0.0) -> pathlib.Path:
    """Report for `localeval bench`: overall + per-depth pp/tg t/s medians,
    then every raw trial. Unlike mmlu/code/ifeval, bench has no pass/fail
    scoring - the "score" here is throughput, not correctness."""
    model = config.get("model") or "unknown-model"
    path = run_dir / report_filename(model)

    lines = [
        "# localeval bench report",
        "",
        f"- generated: {datetime.now(timezone.utc).isoformat()}",
        f"- model: {model}",
        f"- base_url: {config.get('base_url')}",
        f"- run_dir: `{run_dir}`",
        "",
        "## Throughput Summary",
        "",
        f"- **Trials:** {summary['total']} ({summary['error']} errored)",
        f"- **Overall pp t/s (median):** {summary['pp_tokens_per_sec_median']}",
        f"- **Overall tg t/s (median):** {summary['tg_tokens_per_sec_median']}",
        f"- **Completed in:** {elapsed_s:.1f}s",
        "",
        "## By depth",
        "",
        "| Depth | Trials | pp t/s (median) | tg t/s (median) | Errors |",
        "|---|---|---|---|---|",
    ]
    for depth, stats in sorted(summary["by_depth"].items(), key=lambda kv: int(kv[0])):
        lines.append(f"| {depth} | {stats['trials']} | {stats['pp_tokens_per_sec_median']} | {stats['tg_tokens_per_sec_median']} | {stats['errors']} |")
    lines.append("")

    lines.extend(
        [
            "## Config",
            "",
            "```json",
            json.dumps(config, indent=2, default=str),
            "```",
            "",
            "## All trials (raw)",
            "",
            "| depth | trial | pp_tokens | tg_tokens | pp t/s | tg t/s | total_ms | ok | error |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for r in results:
        lines.append(f"| {r['depth']} | {r['trial']} | {r['pp_tokens']} | {r['tg_tokens']} | {r['pp_tokens_per_sec']} | {r['tg_tokens_per_sec']} | {r['total_ms']} | {r['ok']} | {r.get('error', '')} |")
    lines.append("")

    path.write_text("\n".join(lines) + "\n")
    return path


def write_global_report(run_dir: pathlib.Path, entries: list, elapsed_s: float) -> pathlib.Path:
    """One combined report for `localeval all`, aggregating every mode
    that ran into a single overall score/rating, plus a per-mode table
    linking to each mode's own report. entries: list of
    {"mode", "model", "summary", "report_path"} dicts, in run order.
    """
    model = entries[0]["model"] if entries else "unknown-model"
    path = run_dir / report_filename(model)

    per_mode_fields = [(e["mode"], score_fields(e["mode"], e["summary"])) for e in entries]
    overall_earned = sum(f["earned"] for _, f in per_mode_fields)
    overall_total = sum(f["total"] for _, f in per_mode_fields)
    overall_run_total = sum(f["run_total"] for _, f in per_mode_fields)
    overall_counts = {"pass": 0, "partial": 0, "fail": 0, "error": 0}
    for _, f in per_mode_fields:
        for k in overall_counts:
            overall_counts[k] += f["counts"].get(k, 0)
    overall_pct = (overall_earned / overall_total * 100) if overall_total else 0.0
    errored = overall_counts["error"]

    lines = [
        "# localeval all report",
        "",
        f"- generated: {datetime.now(timezone.utc).isoformat()}",
        f"- model: {model}",
        f"- run_dir: `{run_dir}`",
        f"- modes: {', '.join(mode for mode, _ in per_mode_fields)}",
        "",
        "## Overall Summary",
        "",
        f"- **Overall Score:** {overall_earned} / {overall_total}",
        f"- **Overall Rating:** {display.rating_for(overall_pct)}",
    ]

    badges = []
    if overall_counts["pass"]:
        badges.append(f"✅ {overall_counts['pass']} passed")
    if overall_counts["partial"]:
        badges.append(f"⚠ {overall_counts['partial']} partial")
    if overall_counts["fail"]:
        badges.append(f"❌ {overall_counts['fail']} failed")
    if errored:
        badges.append(f"⛔ {errored} errored")
    if badges:
        lines.append(f"- **Results:** {'   '.join(badges)}")

    if overall_run_total != overall_total:
        scored_or_partial = overall_total + overall_counts["partial"]
        lines.append(f"- **Coverage:** {scored_or_partial}/{overall_run_total} items produced any response - {errored} never got one.")

    lines.append(f"- **Completed in:** {elapsed_s:.1f}s")
    lines.append("")

    lines.append("## Per-mode results")
    lines.append("")
    lines.append("| Mode | Score | Rating | Report |")
    lines.append("|---|---|---|---|")
    for e in entries:
        f = score_fields(e["mode"], e["summary"])
        sub_pct = (f["earned"] / f["total"] * 100) if f["total"] else 0.0
        try:
            rel_report = pathlib.Path(e["report_path"]).relative_to(run_dir)
        except ValueError:
            rel_report = e["report_path"]
        lines.append(f"| {e['mode']} | {f['earned']}/{f['total']} | {display.rating_for(sub_pct)} | [report]({rel_report}) |")
    lines.append("")

    lines.append("Each mode's own report (linked above) has the full per-item breakdown; this file is only the cross-mode rollup.")

    path.write_text("\n".join(lines) + "\n")
    return path
