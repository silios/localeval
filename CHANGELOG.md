# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Roadmap

- Optional agentic (multi-turn) generation loop for `code` mode.
- Retry/backoff for transient request errors, still under `--concurrency 1` by default.

## [0.1.0] - 2026-07-26

### Added

- `localeval mmlu`: MMLU-style multiple-choice benchmark. Answer extraction
  takes the last `FINAL ANSWER: X` match in a response and treats
  `finish_reason == "length"` as authoritative TRUNCATED, regardless of
  any text present - the specific failure mode that produced a false
  22.8% score in a previous harness.
- `localeval code`: folder-based code generation benchmark (`task.md` +
  `verify.sh`/`verify.py` per task), with a configurable verify timeout
  distinct from a real failure.
- `localeval ifeval`: hand-rolled instruction-following constraint
  checks (word/sentence/paragraph/bullet counts, include/exclude words,
  JSON validity, case, forbidden letters, prefix/suffix), no ML judging.
- `localeval all`: runs any combination of the three modes under one
  timestamped run directory.
- Every run writes `config.json`, `results.jsonl` (full request + full,
  untruncated raw response per item), and `summary.json` under
  `runs/<mode>/<timestamp>/`.
- Unit tests for the MMLU answer-extraction logic and the ifeval
  constraint checkers.
