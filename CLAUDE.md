# localeval - project instructions

Personal benchmarking CLI for local LLMs served via a llama.cpp
OpenAI-compatible endpoint. KISS: a small handful of files, no framework,
no plugin system, no config DSL unless explicitly requested.

## Feature workflow (TDD)

Every new feature or non-trivial fix in this repo follows this loop, in
order. Don't skip a step or reorder them.

1. **Plan** - state the feature in one or two sentences: what changes,
   which file(s) it touches, what the new/changed CLI surface or output
   shape looks like. Ask one focused question if anything is ambiguous
   (input format, default value, edge-case behavior). Do not write code
   during this step.
2. **Create** - write a failing test first for the new behavior (or the
   bug being fixed), then implement the smallest change that makes it
   pass. Keep functions small and pure where possible (this is why the
   ifeval checkers and the answer-extraction logic are plain
   input -> output functions with no side effects).
3. **Test** - run the full suite (`pytest tests/ -q`), not just the new
   test. If the change touches request/response handling, do a real
   smoke test against the local server (`http://localhost:8080` by
   default) with a tiny sample, and actually look at the resulting
   `results.jsonl` - don't assume the summary numbers are correct without
   reading at least one raw entry.
4. **Update docs** - README.md first (new flags, new file formats, new
   outcome statuses), then CHANGELOG.md (`[Unreleased]` section, moved
   into a version section on release). If a new constraint type,
   outcome status, or file format is added, it must appear in the README
   table/list for its mode.
5. **Offer to commit** - once tests pass and docs are updated, propose a
   Conventional Commits message (`feat:`, `fix:`, `refactor:`, `test:`,
   `docs:`) summarizing the change, and ask before committing. One
   logical change per commit; don't mix refactoring with feature work.

## Things not to repeat

- Never cap `max_tokens` low "for speed." This produced a false 22.8%
  MMLU score before (truncated reasoning + first-letter-token matching
  against echoed options). `finish_reason == "length"` must always be
  checked and always wins over any extracted answer.
- Never truncate or excerpt raw model responses in `results.jsonl` - log
  the full text, every time. This is what made the original bug
  invisible.
- Don't default `--concurrency` above 1. This targets a single-GPU,
  single-agent local box.
