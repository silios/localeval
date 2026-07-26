"""Run-directory management and results reporting.

Every invocation writes a timestamped directory under runs/<mode>/<ts>/
containing:
  config.json    - the full config used for the run
  results.jsonl  - one JSON object per question/task/case, including the
                   full request sent and the full raw response received
  summary.json   - the final summary (see localeval.display for the
                   terminal presentation of this data)
"""

from __future__ import annotations

import dataclasses
import json
import math
import pathlib
from datetime import datetime, timezone


def apply_limit(items: list, limit: int | None) -> list:
    """Evenly stride-sample down to `limit` items instead of taking a
    biased first-N slice. Question/task/case banks are often grouped by
    category (e.g. easy math first, law/ethics last); a plain [:limit]
    slice would only ever sample the start of that ordering, making
    --limit systematically optimistic instead of representative.
    """
    if not limit or limit >= len(items):
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def make_run_dir(runs_root: pathlib.Path, mode: str) -> pathlib.Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = runs_root / mode / ts
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_config(run_dir: pathlib.Path, config: dict) -> None:
    with open(run_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2, default=str)


class ResultsWriter:
    """Appends one JSON object per line to results.jsonl as items complete."""

    def __init__(self, run_dir: pathlib.Path):
        self._path = run_dir / "results.jsonl"
        self._fh = open(self._path, "a")

    def write(self, record: dict) -> None:
        self._fh.write(json.dumps(record, default=_json_default) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def _json_default(obj):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return str(obj)


def write_summary(run_dir: pathlib.Path, summary: dict) -> None:
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)


def latency_stats(results: list) -> dict:
    """Compute p50/p95 TTFT and tokens/sec from a list of result records.

    Only records with ttft_ms > 0 and tokens_per_second > 0 are included
    (errors and records from pre-timing runs have defaults of 0.0).
    Returns an empty dict when no timing data is available.
    """
    ttft_vals = sorted(r["ttft_ms"] for r in results if r.get("ttft_ms", 0) > 0)
    tps_vals = sorted(r["tokens_per_second"] for r in results if r.get("tokens_per_second", 0) > 0)

    if not ttft_vals:
        return {}

    def _pctl(sorted_vals: list, p: float) -> float:
        if not sorted_vals:
            return 0.0
        k = (p / 100) * (len(sorted_vals) - 1)
        lo = int(k)
        hi = min(lo + 1, len(sorted_vals) - 1)
        frac = k - lo
        return round(sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo]), 1)

    return {
        "ttft_p50_ms": _pctl(ttft_vals, 50),
        "ttft_p95_ms": _pctl(ttft_vals, 95),
        "tps_p50": _pctl(tps_vals, 50),
        "tps_p95": _pctl(tps_vals, 95),
        "timed_items": len(ttft_vals),
    }


def score_fields(mode: str, summary: dict) -> dict:
    """Derive the (earned, total, run_total, counts) fields used by both
    the terminal final panel and the per-run report, so the two never
    drift out of sync with each other.
    """
    if mode == "mmlu":
        earned = summary["correct"]
        total = summary["correct"] + summary["wrong"]
        counts = {
            "pass": summary["correct"],
            "partial": summary.get("truncated", 0) + summary.get("no_answer", 0),
            "fail": summary["wrong"],
            "error": summary.get("error", 0),
        }
    elif mode == "code":
        earned = summary["pass"]
        total = summary["pass"] + summary["fail"]
        counts = {
            "pass": summary["pass"],
            "partial": summary.get("timeout", 0) + summary.get("no_code_block", 0) + summary.get("truncated", 0),
            "fail": summary["fail"],
            "error": summary.get("error", 0),
        }
    elif mode == "ifeval":
        earned = summary["pass"]
        total = summary["pass"] + summary["fail"]
        counts = {
            "pass": summary["pass"],
            "partial": summary.get("other", 0) + summary.get("truncated", 0),
            "fail": summary["fail"],
            "error": summary.get("error", 0),
        }
    else:
        raise ValueError(f"unknown mode: {mode}")

    latency = summary.get("latency", {}) or {}
    return {
        "earned": earned,
        "total": total,
        "run_total": summary["total"],
        "counts": counts,
        "latency": latency,
    }
