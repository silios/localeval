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
import pathlib
from datetime import datetime, timezone


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
