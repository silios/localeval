"""localeval CLI entry point."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from . import bench, code, compare, display, ifeval, mmlu, report
from .client import ChatConfig
from .reporting import ResultsWriter, make_run_dir, score_fields, write_config, write_summary

MODE_MODULES = {"mmlu": mmlu, "code": code, "ifeval": ifeval}

import fnmatch


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default="http://localhost:8080", help="OpenAI-compatible base URL")
    parser.add_argument("--model", default="", help="Model name, for logging only")
    parser.add_argument("--api-key", default="", help="API key, if the endpoint requires one")
    parser.add_argument("--max-tokens", type=int, default=4096, help="max_tokens per request")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP request timeout in seconds")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent in-flight requests")
    parser.add_argument("--runs-dir", default="runs", help="Root directory for run outputs")
    parser.add_argument("--retries", type=int, default=2, help="Retries on transient request failures (not on a real response)")
    parser.add_argument("--retry-backoff", type=float, default=1.0, help="Seconds to wait before the first retry, doubling each attempt")
    parser.add_argument("--system-prompt", default=None, help="Override the system prompt for all requests")
    parser.add_argument("--prompt-file", default=None, help="Read system prompt from a file")


def build_chat_config(args) -> ChatConfig:
    system_prompt = ""
    if args.system_prompt:
        system_prompt = args.system_prompt
    elif args.prompt_file:
        system_prompt = pathlib.Path(args.prompt_file).read_text().strip()

    return ChatConfig(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        retry_backoff=args.retry_backoff,
        system_prompt=system_prompt,
    )


def run_config_dict(args, mode: str) -> dict:
    return {
        "mode": mode,
        "base_url": args.base_url,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "timeout": args.timeout,
        "concurrency": args.concurrency,
        "retries": args.retries,
        "retry_backoff": args.retry_backoff,
    }


def cmd_mmlu(args, run_dir: pathlib.Path = None) -> dict:
    if args.dry_run:
        return _dry_run_mmlu(args)

    config = build_chat_config(args)
    questions = mmlu.load_questions(args.questions)

    if run_dir is None:
        run_dir = make_run_dir(pathlib.Path(args.runs_dir), "mmlu")
    cfg = run_config_dict(args, "mmlu")
    cfg["questions_file"] = args.questions
    cfg["limit"] = args.limit
    write_config(run_dir, cfg)

    writer = ResultsWriter(run_dir)
    start = time.monotonic()
    try:
        summary, results = mmlu.run(config, questions, args.concurrency, writer, limit=args.limit)
    finally:
        writer.close()
    elapsed = time.monotonic() - start

    write_summary(run_dir, summary)
    fields = score_fields("mmlu", summary)
    report_path = report.write_report(run_dir, "mmlu", cfg, summary, results, elapsed_s=elapsed)

    breakdown_rows = []
    for cat, stats in summary["by_category"].items():
        earned_str = f"{stats['correct']}/{stats['correct'] + stats['wrong']}"
        if stats["error"]:
            earned_str += f" ({stats['error']} errored)"
        breakdown_rows.append((cat, stats["accuracy_pct"], earned_str))
    display.print_breakdown("Category Breakdown", breakdown_rows)
    display.print_final_panel(
        mode="mmlu",
        model=args.model,
        earned=fields["earned"],
        total=fields["total"],
        counts=fields["counts"],
        elapsed_s=elapsed,
        report_path=report_path,
        run_total=fields["run_total"],
        latency=fields["latency"],
    )
    return {"mode": "mmlu", "model": args.model, "summary": summary, "report_path": report_path}


def cmd_code(args, run_dir: pathlib.Path = None) -> dict:
    if args.dry_run:
        return _dry_run_code(args)

    config = build_chat_config(args)
    tasks = code.load_tasks(args.tasks_dir)

    if run_dir is None:
        run_dir = make_run_dir(pathlib.Path(args.runs_dir), "code")
    cfg = run_config_dict(args, "code")
    cfg["tasks_dir"] = args.tasks_dir
    cfg["verify_timeout"] = args.verify_timeout
    cfg["limit"] = args.limit
    write_config(run_dir, cfg)

    scratch_root = pathlib.Path(args.scratch_dir) if args.scratch_dir else run_dir / "scratch"
    scratch_root.mkdir(parents=True, exist_ok=True)

    writer = ResultsWriter(run_dir)
    start = time.monotonic()
    try:
        summary, results = code.run(config, tasks, scratch_root, args.verify_timeout, writer, limit=args.limit)
    finally:
        writer.close()
    elapsed = time.monotonic() - start

    write_summary(run_dir, summary)
    fields = score_fields("code", summary)
    report_path = report.write_report(run_dir, "code", cfg, summary, results, elapsed_s=elapsed)

    display.print_final_panel(
        mode="code",
        model=args.model,
        earned=fields["earned"],
        total=fields["total"],
        counts=fields["counts"],
        elapsed_s=elapsed,
        report_path=report_path,
        run_total=fields["run_total"],
        latency=fields["latency"],
    )
    return {"mode": "code", "model": args.model, "summary": summary, "report_path": report_path}


def cmd_ifeval(args, run_dir: pathlib.Path = None) -> dict:
    if args.dry_run:
        return _dry_run_ifeval(args)

    config = build_chat_config(args)
    cases = ifeval.load_cases(args.cases)

    if run_dir is None:
        run_dir = make_run_dir(pathlib.Path(args.runs_dir), "ifeval")
    cfg = run_config_dict(args, "ifeval")
    cfg["cases_file"] = args.cases
    cfg["limit"] = args.limit
    write_config(run_dir, cfg)

    writer = ResultsWriter(run_dir)
    start = time.monotonic()
    try:
        summary, results = ifeval.run(config, cases, writer, limit=args.limit)
    finally:
        writer.close()
    elapsed = time.monotonic() - start

    write_summary(run_dir, summary)
    fields = score_fields("ifeval", summary)
    report_path = report.write_report(run_dir, "ifeval", cfg, summary, results, elapsed_s=elapsed)

    breakdown_rows = []
    for ct, stats in summary["by_constraint"].items():
        earned_str = f"{stats['pass']}/{stats['pass'] + stats['fail']}"
        if stats["error"]:
            earned_str += f" ({stats['error']} errored)"
        breakdown_rows.append((ct, stats["pass_rate_pct"], earned_str))
    display.print_breakdown("Constraint Breakdown", breakdown_rows)
    display.print_final_panel(
        mode="ifeval",
        model=args.model,
        earned=fields["earned"],
        total=fields["total"],
        counts=fields["counts"],
        elapsed_s=elapsed,
        report_path=report_path,
        run_total=fields["run_total"],
        latency=fields["latency"],
    )
    return {"mode": "ifeval", "model": args.model, "summary": summary, "report_path": report_path}


def cmd_all(args) -> dict:
    if args.dry_run:
        return _dry_run_all(args)

    if not (args.questions or args.tasks_dir or args.cases):
        print("error: `all` needs at least one of --questions, --tasks-dir, --cases", file=sys.stderr)
        sys.exit(1)

    run_dir = make_run_dir(pathlib.Path(args.runs_dir), "all")
    entries = []
    start = time.monotonic()

    if args.questions:
        sub_dir = run_dir / "mmlu"
        sub_dir.mkdir(parents=True)
        entries.append(cmd_mmlu(args, run_dir=sub_dir))

    if args.tasks_dir:
        sub_dir = run_dir / "code"
        sub_dir.mkdir(parents=True)
        entries.append(cmd_code(args, run_dir=sub_dir))

    if args.cases:
        sub_dir = run_dir / "ifeval"
        sub_dir.mkdir(parents=True)
        entries.append(cmd_ifeval(args, run_dir=sub_dir))

    elapsed = time.monotonic() - start

    results = {e["mode"]: e["summary"] for e in entries}
    write_summary(run_dir, results)

    global_report_path = report.write_global_report(run_dir, entries, elapsed_s=elapsed)
    display.print_global_panel(entries, elapsed_s=elapsed, report_path=global_report_path)

    return results


class _NullWriter:
    """Discards records instead of appending to results.jsonl.

    resume_run reruns only a subset of items and merges them back into
    the full results.jsonl itself, so the per-item incremental append
    that ResultsWriter does during a fresh run would just leave stray
    partial data behind.
    """

    def write(self, record: dict) -> None:
        pass

    def close(self) -> None:
        pass


def resume_run(run_dir: pathlib.Path, config: ChatConfig, concurrency: int, verify_timeout: int = None) -> dict:
    """Rerun only the errored items from an existing run, updating it in place.

    "Errored" means a request failure (network error, non-200, malformed
    response) - not truncated/wrong/no_answer/fail, which are legitimate
    scoring outcomes, not something to silently retry away.
    """
    config_path = run_dir / "config.json"
    results_path = run_dir / "results.jsonl"

    with open(config_path) as f:
        cfg = json.load(f)
    mode = cfg["mode"]
    if mode not in MODE_MODULES:
        raise ValueError(f"resume is not supported for mode {mode!r}")

    records = []
    with open(results_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    key_field = "name" if mode == "code" else "id"
    errored_keys = {r[key_field] for r in records if r["status"] == "error"}

    if not errored_keys:
        return {"mode": mode, "resumed": 0, "run_dir": run_dir}

    writer = _NullWriter()
    start = time.monotonic()
    if mode == "mmlu":
        questions = mmlu.load_questions(cfg["questions_file"])
        subset = [q for q in questions if q.id in errored_keys]
        _, new_records = mmlu.run(config, subset, concurrency, writer, limit=None)
    elif mode == "code":
        tasks = code.load_tasks(cfg["tasks_dir"])
        subset = [t for t in tasks if t["name"] in errored_keys]
        scratch_root = run_dir / "scratch"
        scratch_root.mkdir(parents=True, exist_ok=True)
        vt = verify_timeout if verify_timeout is not None else cfg.get("verify_timeout", 120)
        _, new_records = code.run(config, subset, scratch_root, vt, writer, limit=None)
    else:
        cases = ifeval.load_cases(cfg["cases_file"])
        subset = [c for c in cases if c.id in errored_keys]
        _, new_records = ifeval.run(config, subset, writer, limit=None)
    elapsed = time.monotonic() - start

    by_key = {r[key_field]: r for r in new_records}
    merged = [by_key.get(r[key_field], r) for r in records]

    with open(results_path, "w") as f:
        for r in merged:
            f.write(json.dumps(r, default=str) + "\n")

    summary = MODE_MODULES[mode].summarize(merged)
    write_summary(run_dir, summary)

    for old_report in run_dir.glob("*-report.md"):
        old_report.unlink()
    report_path = report.write_report(run_dir, mode, cfg, summary, merged, elapsed_s=elapsed)

    return {
        "mode": mode,
        "resumed": len(errored_keys),
        "still_errored": sum(1 for r in merged if r["status"] == "error"),
        "summary": summary,
        "elapsed_s": elapsed,
        "report_path": report_path,
        "run_dir": run_dir,
    }


def cmd_resume(args) -> dict:
    run_dir = pathlib.Path(args.run_dir)
    if not (run_dir / "config.json").exists() or not (run_dir / "results.jsonl").exists():
        print(f"error: {run_dir} is not a run directory (missing config.json/results.jsonl)", file=sys.stderr)
        sys.exit(1)

    with open(run_dir / "config.json") as f:
        cfg = json.load(f)

    config = ChatConfig(
        base_url=args.base_url if args.base_url is not None else cfg["base_url"],
        model=args.model if args.model is not None else cfg["model"],
        api_key=args.api_key if args.api_key is not None else cfg.get("api_key", ""),
        max_tokens=args.max_tokens if args.max_tokens is not None else cfg["max_tokens"],
        timeout=args.timeout if args.timeout is not None else cfg["timeout"],
        retries=args.retries if args.retries is not None else cfg.get("retries", 2),
        retry_backoff=args.retry_backoff if args.retry_backoff is not None else cfg.get("retry_backoff", 1.0),
    )
    concurrency = args.concurrency if args.concurrency is not None else cfg.get("concurrency", 1)

    result = resume_run(run_dir, config, concurrency, verify_timeout=args.verify_timeout)

    if result["resumed"] == 0:
        print(f"Nothing to resume: no errored items in {run_dir}")
        return result

    mode = result["mode"]
    summary = result["summary"]
    fields = score_fields(mode, summary)

    if mode == "mmlu":
        breakdown_rows = []
        for cat, stats in summary["by_category"].items():
            earned_str = f"{stats['correct']}/{stats['correct'] + stats['wrong']}"
            if stats["error"]:
                earned_str += f" ({stats['error']} errored)"
            breakdown_rows.append((cat, stats["accuracy_pct"], earned_str))
        display.print_breakdown("Category Breakdown", breakdown_rows)
    elif mode == "ifeval":
        breakdown_rows = []
        for ct, stats in summary["by_constraint"].items():
            earned_str = f"{stats['pass']}/{stats['pass'] + stats['fail']}"
            if stats["error"]:
                earned_str += f" ({stats['error']} errored)"
            breakdown_rows.append((ct, stats["pass_rate_pct"], earned_str))
        display.print_breakdown("Constraint Breakdown", breakdown_rows)

    display.print_final_panel(
        mode=mode,
        model=config.model,
        earned=fields["earned"],
        total=fields["total"],
        counts=fields["counts"],
        elapsed_s=result["elapsed_s"],
        report_path=result["report_path"],
        run_total=fields["run_total"],
        latency=fields["latency"],
    )
    print(f"Resumed {result['resumed']} errored item(s); {result['still_errored']} still errored.")
    return result


def cmd_compare(args) -> dict:
    """Compare two run directories of the same mode."""
    dir_a = pathlib.Path(args.run_dir_a)
    dir_b = pathlib.Path(args.run_dir_b)

    for label, d in [("first", dir_a), ("second", dir_b)]:
        if not (d / "config.json").exists():
            print(f"error: {d} is not a run directory (missing config.json)", file=sys.stderr)
            sys.exit(1)
        if not (d / "summary.json").exists():
            print(f"error: {d} has no summary.json (run may be incomplete)", file=sys.stderr)
            sys.exit(1)

    with open(dir_a / "config.json") as f:
        cfg_a = json.load(f)
    with open(dir_b / "config.json") as f:
        cfg_b = json.load(f)

    mode_a = cfg_a.get("mode", "")
    mode_b = cfg_b.get("mode", "")

    if mode_a != mode_b:
        print(f"error: cannot compare runs of different modes ({mode_a} vs {mode_b})", file=sys.stderr)
        sys.exit(1)

    with open(dir_a / "summary.json") as f:
        summary_a = json.load(f)
    with open(dir_b / "summary.json") as f:
        summary_b = json.load(f)

    result = compare.diff_summaries(mode_a, summary_a, summary_b)
    display.print_compare(result, model_a=cfg_a.get("model", ""), model_b=cfg_b.get("model", ""))
    return result


# ---------------------------------------------------------------------------
# --dry-run helpers: load and validate banks without sending requests
# ---------------------------------------------------------------------------

def _dry_run_mmlu(args) -> dict:
    try:
        questions = mmlu.load_questions(args.questions)
    except Exception as exc:
        print(f"error: failed to load question bank: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.limit and args.limit < len(questions):
        questions = questions[:args.limit]

    cats = {}
    for q in questions:
        cats[q.category] = cats.get(q.category, 0) + 1

    print(f"✓ {len(questions)} questions loaded from {args.questions}")
    print(f"  {len(cats)} categories")
    if cats:
        for cat, count in sorted(cats.items()):
            print(f"    {cat}: {count}")
    return {"mode": "mmlu", "questions": len(questions), "categories": len(cats)}


def _dry_run_code(args) -> dict:
    try:
        tasks = code.load_tasks(args.tasks_dir)
    except Exception as exc:
        print(f"error: failed to load tasks: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.limit and args.limit < len(tasks):
        tasks = tasks[:args.limit]

    print(f"✓ {len(tasks)} tasks loaded from {args.tasks_dir}")
    for t in tasks:
        print(f"    {t['name']}  (verify: {t['verify_path'].name})")
    return {"mode": "code", "tasks": len(tasks)}


def _dry_run_ifeval(args) -> dict:
    try:
        cases = ifeval.load_cases(args.cases)
    except Exception as exc:
        print(f"error: failed to load case file: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.limit and args.limit < len(cases):
        cases = cases[:args.limit]

    from .ifeval import CONSTRAINT_CHECKERS

    unknown = [c for c in cases if c.constraint_type not in CONSTRAINT_CHECKERS]

    print(f"✓ {len(cases)} cases loaded from {args.cases}")
    cts = {}
    for c in cases:
        cts[c.constraint_type] = cts.get(c.constraint_type, 0) + 1
    for ct, count in sorted(cts.items()):
        marker = " [UNKNOWN]" if ct not in CONSTRAINT_CHECKERS else ""
        print(f"    {ct}: {count}{marker}")

    if unknown:
        print(f"\n⚠ {len(unknown)} case(s) with unknown constraint types (will be marked 'unknown_constraint' at eval time):")
        for c in unknown:
            print(f"    {c.id}: {c.constraint_type}")

    return {"mode": "ifeval", "cases": len(cases), "unknown_constraints": len(unknown)}


def _dry_run_all(args) -> dict:
    results = {}
    if args.questions:
        results["mmlu"] = _dry_run_mmlu(args)
    if args.tasks_dir:
        results["code"] = _dry_run_code(args)
    if args.cases:
        results["ifeval"] = _dry_run_ifeval(args)
    if not results:
        print("error: `all --dry-run` needs at least one of --questions, --tasks-dir, --cases", file=sys.stderr)
        sys.exit(1)
    return results


def list_runs(runs_root: pathlib.Path, model_filter: str = None) -> list:
    """Walk a runs directory and return a list of run summary dicts.

    Each dict has: mode, model, timestamp, earned, total, pct, rating,
    errors, run_dir. Sorted newest-first by timestamp. Skips directories
    without both config.json and summary.json.
    """
    results = []
    for mode_dir in sorted(runs_root.iterdir()):
        if not mode_dir.is_dir():
            continue
        for run_dir in sorted(mode_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            cfg_path = run_dir / "config.json"
            sum_path = run_dir / "summary.json"
            if not cfg_path.exists() or not sum_path.exists():
                continue
            try:
                cfg = json.loads(cfg_path.read_text())
                summary = json.loads(sum_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            mode = cfg.get("mode", mode_dir.name)
            model = cfg.get("model", "")
            if model_filter and not fnmatch.fnmatch(model.lower(), model_filter.lower()):
                continue

            fields = score_fields(mode, summary)
            earned = fields["earned"]
            total = fields["total"]
            pct = (earned / total * 100) if total else 0.0
            errors = summary.get("error", 0)

            results.append({
                "mode": mode,
                "model": model,
                "timestamp": run_dir.name,
                "earned": earned,
                "total": total,
                "pct": round(pct, 1),
                "rating": display.rating_for(pct),
                "errors": errors,
                "run_dir": str(run_dir),
            })

    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return results


def cmd_list(args) -> None:
    runs_root = pathlib.Path(args.runs_dir)
    if not runs_root.is_dir():
        print(f"error: {runs_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    runs = list_runs(runs_root, model_filter=args.filter)
    if not runs:
        print(f"No runs found in {runs_root}" + (f" matching '{args.filter}'" if args.filter else ""))
        return

    display.print_list_runs(runs)


def cmd_bench(args) -> dict:
    """Run a throughput benchmark at configurable context depths."""
    config = build_chat_config(args)
    depths = [int(d.strip()) for d in args.depth.split(",")]

    results = bench.run_benchmark(
        config,
        depths=depths,
        pp_tokens=args.pp,
        tg_tokens=args.tg,
        trials=args.trials,
    )

    display.print_bench_results(results, model=config.model, depths=depths)
    return {"mode": "bench", "results": results}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="localeval", description="Benchmark a local LLM via a llama.cpp OpenAI-compatible endpoint")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    p_mmlu = subparsers.add_parser("mmlu", help="MMLU-style multiple-choice benchmark")
    add_common_args(p_mmlu)
    p_mmlu.add_argument("--questions", required=True, help="Path to the JSON question bank")
    p_mmlu.add_argument("--limit", type=int, default=None, help="Only run the first N questions")
    p_mmlu.add_argument("--dry-run", action="store_true", help="Load and validate the question bank without sending requests")
    p_mmlu.set_defaults(func=cmd_mmlu)

    p_code = subparsers.add_parser("code", help="Code generation benchmark")
    add_common_args(p_code)
    p_code.add_argument("--tasks-dir", required=True, help="Directory containing task folders")
    p_code.add_argument("--verify-timeout", type=int, default=120, help="Seconds before a verify run is marked TIMEOUT")
    p_code.add_argument("--scratch-dir", default=None, help="Where generated code is written (default: <run_dir>/scratch)")
    p_code.add_argument("--limit", type=int, default=None, help="Only run the first N tasks")
    p_code.add_argument("--dry-run", action="store_true", help="Load and validate task directories without sending requests")
    p_code.set_defaults(func=cmd_code)

    p_ifeval = subparsers.add_parser("ifeval", help="IFEval-light instruction-following benchmark")
    add_common_args(p_ifeval)
    p_ifeval.add_argument("--cases", required=True, help="Path to the JSON case file")
    p_ifeval.add_argument("--limit", type=int, default=None, help="Only run the first N cases")
    p_ifeval.add_argument("--dry-run", action="store_true", help="Load and validate the case file without sending requests")
    p_ifeval.set_defaults(func=cmd_ifeval)

    p_all = subparsers.add_parser("all", help="Run all applicable modes in one go")
    add_common_args(p_all)
    p_all.add_argument("--questions", default=None, help="Path to the JSON question bank (mmlu)")
    p_all.add_argument("--limit", type=int, default=None, help="Only run the first N questions/tasks/cases (all modes)")
    p_all.add_argument("--tasks-dir", default=None, help="Directory containing task folders (code)")
    p_all.add_argument("--verify-timeout", type=int, default=120, help="Seconds before a verify run is marked TIMEOUT (code)")
    p_all.add_argument("--scratch-dir", default=None, help="Where generated code is written (code)")
    p_all.add_argument("--cases", default=None, help="Path to the JSON case file (ifeval)")
    p_all.add_argument("--dry-run", action="store_true", help="Load and validate all banks without sending requests")
    p_all.set_defaults(func=cmd_all)

    p_resume = subparsers.add_parser("resume", help="Rerun only the errored items from a previous run, updating it in place")
    p_resume.add_argument("run_dir", help="Path to an existing run directory, e.g. runs/mmlu/20260726T193151Z")
    p_resume.add_argument("--base-url", default=None, help="Override the base URL stored in the original run's config")
    p_resume.add_argument("--model", default=None, help="Override the model name stored in the original run's config")
    p_resume.add_argument("--api-key", default=None, help="Override the API key stored in the original run's config")
    p_resume.add_argument("--max-tokens", type=int, default=None, help="Override max_tokens stored in the original run's config")
    p_resume.add_argument("--timeout", type=int, default=None, help="Override the request timeout stored in the original run's config")
    p_resume.add_argument("--concurrency", type=int, default=None, help="Override concurrency stored in the original run's config")
    p_resume.add_argument("--retries", type=int, default=None, help="Override retries stored in the original run's config")
    p_resume.add_argument("--retry-backoff", type=float, default=None, help="Override retry backoff stored in the original run's config")
    p_resume.add_argument("--verify-timeout", type=int, default=None, help="Override verify timeout stored in the original run's config (code mode)")
    p_resume.set_defaults(func=cmd_resume)

    p_compare = subparsers.add_parser("compare", help="Side-by-side diff of two run directories")
    p_compare.add_argument("run_dir_a", help="Path to the first (baseline) run directory")
    p_compare.add_argument("run_dir_b", help="Path to the second (comparison) run directory")
    p_compare.set_defaults(func=cmd_compare)

    p_list = subparsers.add_parser("list", help="List past runs with scores and ratings")
    p_list.add_argument("--runs-dir", default="runs", help="Root directory for run outputs")
    p_list.add_argument("--filter", default=None, help="Filter by model name (glob, e.g. 'qwen*')")
    p_list.set_defaults(func=cmd_list)

    p_bench = subparsers.add_parser("bench", help="Throughput benchmark at configurable context depths")
    add_common_args(p_bench)
    p_bench.add_argument("--pp", type=int, default=2048, help="Prompt processing tokens")
    p_bench.add_argument("--tg", type=int, default=128, help="Text generation tokens")
    p_bench.add_argument("--depth", default="0,4096,8192,16384", help="Comma-separated context depths to test")
    p_bench.add_argument("--trials", type=int, default=3, help="Number of runs per depth")
    p_bench.set_defaults(func=cmd_bench)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
