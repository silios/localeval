# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `localeval bench`'s `pp_tokens_per_sec` was unreliable on any backend
  that ignores the llama.cpp-specific `"cache_prompt": false` extension
  (confirmed on LM Studio) - since every trial at a given depth sent
  the byte-identical prompt, the server's own prefix/KV cache made
  trial 2+ measure a cache hit instead of real prompt processing,
  producing values that swung wildly between trials and were sometimes
  *higher* at a larger context depth than a smaller one. Every trial's
  prompt is now prefixed with a nonce unique to its (depth, trial) pair,
  so no two trials can ever share a cacheable prefix, regardless of
  whether the backend honors `cache_prompt`. `cache_prompt: false` is
  still sent for llama.cpp.

- Fixing the above surfaced a second, previously-hidden bug: deriving
  `tg_time_ms` by subtracting one request's `pp_time_ms` from a
  *different* request's `total_ms` can go negative under normal
  request-to-request timing jitter, especially on small/fast models
  where per-request overhead rivals actual compute time. This was
  floored to a minimum and reported anyway, producing nonsense values
  like `64,000 t/s`. Such trials are now marked invalid (`status:
  "error"`, with an explanatory message) and excluded from the
  pp/tg t/s medians, instead of silently reporting a fake number -
  confirmed against LM Studio, which now correctly reports several
  `d2048` trials as invalid rather than absurd throughput.

### Changed

- `localeval bench`'s terminal output is now a single bordered panel
  (header info, per-depth table, and report link all inside one box),
  matching the final-summary panel style every other mode uses, instead
  of a header panel followed by a separate free-floating table. A
  failed trial now flips the panel to the same red/"Incomplete" styling
  `print_final_panel` uses for errored runs.

- Refreshed `assets/localeval-all-output.svg` to reflect the current
  code base (previously predated most of the code-task bank, the
  system-prompt override, and the border-color fix above). Added
  `assets/localeval-bench-output.svg` showing `localeval bench`'s
  throughput output, since bench didn't exist when the README's
  screenshot was last generated.

### Fixed

- `tokens_per_second`/`total_tokens` were always `0.0`/`0` in
  `results.jsonl`, `summary.json`'s `latency` object, and the terminal
  panel for `mmlu`/`code`/`ifeval` (every mode using the streaming
  request path). The OpenAI streaming API only includes a `usage`
  block in the final SSE chunk when the request sets
  `"stream_options": {"include_usage": true}` - this was never sent, so
  `usage` was always empty and `completion_tokens` always defaulted to
  `0`. TTFT was unaffected since it's measured independently of usage
  data. Added the missing `stream_options` field to the streaming
  request payload; verified against the live server that
  `total_tokens`/`tokens_per_second` are now populated per item.

- `localeval list`'s trailer hint (the path printed under the table)
  used `run_dir.rsplit('/', 3)[0]` plus the mode name, which only
  produced the right path by coincidence when `--runs-dir` was the
  default `runs` - any deeper `--runs-dir` had its own directory name
  truncated away. Replaced with the actual parent directory of
  `run_dir`, which is correct regardless of how deep `--runs-dir` is.

- `localeval bench` now persists its run like every other mode:
  `config.json`/`results.jsonl` (one line per trial)/`summary.json`
  (median pp/tg t/s overall and per context depth)/a report under
  `runs/bench/<timestamp>/`. Previously bench only printed a table and
  discarded the data, so a bench run couldn't be listed or compared
  later. `localeval list` now shows bench runs (with a throughput score
  instead of pass/fail), and `localeval compare` diffs two bench runs'
  pp/tg t/s medians, overall and per depth.

- `print_final_panel`/`print_global_panel` had the success/incomplete
  panel border colors swapped: a fully successful run showed a red
  border and a run with errors showed yellow. Corrected so errored runs
  are red and complete runs are yellow.

- Added `requirements.txt` (`requests`, `rich`, unpinned). Nothing
  previously declared these anywhere in the repo, so a clean clone had
  no reliable way to know what to install. `README.md`'s setup steps
  now install from it.

- `--dry-run --limit N` now uses the same stride-sampling
  (`reporting.apply_limit`) as a real run, instead of a plain `[:N]`
  slice. Previously `--dry-run --limit N` could preview a different
  subset of the bank than what a real `--limit N` run would actually
  send, defeating the point of dry-run as a pre-flight check.

- `config.json` now records `api_key`, `system_prompt`, and (for `code`)
  `scratch_dir`. Previously these were silently dropped, so `localeval
  resume` on a run made with a custom `--system-prompt`/`--prompt-file`,
  `--api-key`, or `--scratch-dir` would revert to the per-mode default
  prompt, send no auth header, or write to the wrong scratch dir.
  `resume` also gained `--system-prompt`/`--prompt-file`/`--scratch-dir`
  overrides, matching the existing pattern for other options.

### Added

- `localeval quick`/`medium`/`long`/`ultra`: shortcuts for `all` against
  the bundled sample banks (`sample_data/mmlu-test-bank-200.md`,
  `sample_data/code_tasks`, `sample_data/ifeval_sample.json`) at a fixed
  `--limit` (`quick=10`, `medium=20`, `long=50`, `ultra`=full banks, no
  limit), so a sanity check against a running server doesn't need
  `--questions`/`--tasks-dir`/`--cases`/`--limit` spelled out every
  time. All shared options still apply; bank paths are not overridable
  on these presets - use `all` directly for a custom bank. Unless
  `--dry-run` is given, each preset also runs a small throughput bench
  first (3 context depths, 1 trial each, `--pp 512 --tg 64`), persisted
  under `runs/bench/<timestamp>/` like a standalone `bench` run, as a
  baseline read before the capability tests.

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
