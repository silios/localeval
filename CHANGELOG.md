# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `config.json` now records `api_key`, `system_prompt`, and (for `code`)
  `scratch_dir`. Previously these were silently dropped, so `localeval
  resume` on a run made with a custom `--system-prompt`/`--prompt-file`,
  `--api-key`, or `--scratch-dir` would revert to the per-mode default
  prompt, send no auth header, or write to the wrong scratch dir.
  `resume` also gained `--system-prompt`/`--prompt-file`/`--scratch-dir`
  overrides, matching the existing pattern for other options.

### Added

- All requests are now sent with `stream: true` (SSE) instead of a
  blocking JSON response, so time-to-first-token (TTFT) and
  tokens-per-second can be measured per item. `ChatResult` gains
  `ttft_ms`, `total_tokens`, and `tokens_per_second`; these flow through
  every mode to `results.jsonl`, are aggregated as p50/p95 into
  `summary.json` (`latency` object), and are surfaced in the final
  terminal panel and the per-run report. Backward-compatible: the SSE
  stream is parsed on the fly and a synthetic non-streaming response
  dict is stored as `raw_response`, so every downstream consumer sees
  the same shape it always has.

- `localeval compare <run-dir-1> <run-dir-2>`: side-by-side diff of two
  run directories of the same mode. Pure read-only analysis: loads
  `summary.json` from each, diffs overall score (Δ earned, Δ pct),
  per-category/per-constraint breakdown with colored deltas, and latency
  (p50/p95 TTFT and tokens/sec). Positive deltas are green (run 2 did
  better), negative are red (regression). Useful for A/B testing model
  versions, quantization levels, or prompt changes.

- `localeval resume <run_dir>`: reruns only the items still marked

- `localeval list`: walks the `runs/` directory and prints a Rich table
  of every completed run: mode, model, timestamp, score, star rating,
  and error count. Optional `--filter` for model name glob (e.g.
  `--filter "qwen*"`). Tolerant of older `summary.json` files that may
  lack fields added in later versions.

- `--dry-run` flag for `mmlu`, `code`, `ifeval`, and `all`: loads and
  validates the question/task/case bank without sending a single
  request. Prints item counts, category breakdowns, and flags unknown
  constraint types. Catches malformed data (missing options, bad JSON,
  missing answer keys) before committing to a long run.

- `--system-prompt` and `--prompt-file` flags for all modes: override
  the system prompt sent with every request. `--prompt-file` reads from
  a file. Unlocks prompt engineering experiments (chain-of-thought,
  role-playing) without code changes. For mmlu, the default prompt
  includes a `FINAL ANSWER: X` instruction - override must include it.

- `localeval bench`: throughput benchmark that measures raw server
  performance: prompt processing speed (pp t/s) and text generation
  speed (tg t/s) at configurable context depths. Uses non-streaming
  requests to get accurate `usage.prompt_tokens` and
  `usage.completion_tokens`. Sends `"cache_prompt": false` (llama.cpp
  extension) so repeated trials against the same prompt aren't
  artificially sped up by prompt-prefix caching. Configurable via
  `--pp`, `--tg`, `--depth` (comma-separated depths), and `--trials`.
  Run first to establish baseline throughput before capability
  benchmarks.

- `localeval resume <run_dir>`: reruns only the items still marked
  `error` in an existing run (reloading the original question/task/case
  bank), and merges the result back into that run directory in place -
  `results.jsonl`, `summary.json`, and the report are all updated,
  every other item is left untouched, and the stale report is replaced
  rather than left alongside the new one. Any shared option can be
  overridden on resume; anything omitted falls back to the original
  run's `config.json`. A no-op (with a message, no file changes) if
  nothing is left in `error` state.

- `--retries` (default `2`) and `--retry-backoff` (default `1.0`, doubling
  each attempt) for all modes: transient request failures (connection
  errors, non-200 status, malformed JSON/response shape) are now retried
  automatically. A successful response is never retried, including a
  truncated one (`finish_reason == "length"`) - that is real signal
  about the model's output, not a transient fault. `results.jsonl` now
  records `attempts` per item so a retried request is visible in the
  raw data.

- `localeval all` now writes one additional global report at the top of
  the run directory, aggregating every mode that ran into a single
  overall score/rating/coverage view, with a per-mode table linking to
  each mode's own report - alongside the existing per-mode
  (mmlu/code/ifeval) reports, which are unchanged. The terminal also
  prints a combined "All Benchmarks Complete/Incomplete" panel after
  all included modes finish.
- The per-run report file now includes a "Benchmark Summary" section
  with the same score, star rating, pass/partial/fail/errored badges,
  and coverage line shown in the terminal's final panel - previously
  the report only had the raw JSON summary, not this readable form.
  Both are now derived from the same `reporting.score_fields()` helper
  so they can't drift out of sync with each other.
- `--limit N` is now available on `code` and `ifeval` (previously only
  `mmlu`), and applies to every mode included in an `all` run - useful
  for a quick partial run before committing to a full one.

### Fixed

- `code` and `ifeval` modes now check `finish_reason == "length"` and
  mark the item TRUNCATED, matching `mmlu`'s existing behavior. Before
  this fix, a cut-off response in `code` mode got written to disk and
  verified anyway (an almost-certain false `fail`), and in `ifeval`
  mode got checked against its constraint anyway (which can produce
  both false passes - e.g. `no_commas` is trivially satisfied by less
  text - and false fails, e.g. `valid_json`). Neither mode had a
  `truncated` bucket at all previously.
- `--limit N` now takes an evenly-strided sample across the whole bank
  (`reporting.apply_limit`) instead of a plain first-N slice. Banks are
  often grouped by category, so first-N systematically sampled the easy
  end and reported an optimistic score a full run wouldn't back up -
  the same class of "hides the real number" problem this tool exists to
  avoid.

- The final terminal summary panel and category/constraint breakdown no
  longer hide request errors. A run where the server dropped mid-way
  (e.g. restarted to change `--parallel`) used to show a clean-looking
  "82/82, Excellent" score with no indication that 117 of 200 questions
  never got a response - errors were silently excluded from every
  visible count. The panel now shows an explicit `⛔ N errored` badge, a
  `Coverage: X/Y items produced any response` line whenever it differs
  from the scored total, and switches its title to "⚠️ Benchmark
  Incomplete" (yellow border) instead of "🏆 Benchmark Complete" when
  any item errored. Per-category/per-constraint breakdown rows also
  append `(N errored)` to their Earned column. ifeval's summary now
  separates `error` (request failures) from `other` (bad
  constraint_type/constraint_params) instead of conflating both into one
  vague bucket.

### Added

- MMLU question banks can now also be loaded from a plain-text `.md`/`.txt`
  format (category headings + numbered question lines + a separate
  answer key section), alongside the existing `.json` format, dispatched
  by file extension.
- Rich-based terminal display styled after `tool-eval-bench`'s UI: a
  live progress bar with a running pass/fail tally, a colored
  category/constraint breakdown table, and a boxed final summary panel
  with a 1-5 star rating. Adds `rich` as a dependency.
- Per-run human-readable debug report (`<date>-<model>-<uuid>-report.md`)
  written alongside `config.json`/`results.jsonl`/`summary.json` for
  `mmlu`, `code`, and `ifeval` runs: config + summary, every
  non-passing item with details and a response excerpt, and a compact
  table of all items. `results.jsonl` remains the full raw backing data.

### Roadmap

- `localeval sweep`: run the same benchmark across a parameter sweep
  (e.g. `--sweep temperature=0.0,0.3,0.7,1.0`), writing each setting
  into its own sub-directory with an aggregated comparison summary.
- Needle-in-a-haystack (`localeval niah`) mode: long-context retrieval
  benchmark. Insert known facts at varying depths into filler text of
  configurable length, test whether the model retrieves them. The
  biggest differentiator between local models right now.
- Optional agentic (multi-turn) generation loop for `code` mode.

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
