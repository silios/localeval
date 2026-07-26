"""localeval CLI entry point."""

from __future__ import annotations

import argparse
import pathlib
import sys

from . import code, ifeval, mmlu
from .client import ChatConfig
from .reporting import ResultsWriter, make_run_dir, print_summary, write_config, write_summary


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default="http://localhost:8080", help="OpenAI-compatible base URL")
    parser.add_argument("--model", default="", help="Model name, for logging only")
    parser.add_argument("--api-key", default="", help="API key, if the endpoint requires one")
    parser.add_argument("--max-tokens", type=int, default=4096, help="max_tokens per request")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP request timeout in seconds")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent in-flight requests")
    parser.add_argument("--runs-dir", default="runs", help="Root directory for run outputs")


def build_chat_config(args) -> ChatConfig:
    return ChatConfig(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )


def run_config_dict(args, mode: str) -> dict:
    return {
        "mode": mode,
        "base_url": args.base_url,
        "model": args.model,
        "max_tokens": args.max_tokens,
        "timeout": args.timeout,
        "concurrency": args.concurrency,
    }


def cmd_mmlu(args, run_dir: pathlib.Path = None) -> dict:
    config = build_chat_config(args)
    questions = mmlu.load_questions(args.questions)

    if run_dir is None:
        run_dir = make_run_dir(pathlib.Path(args.runs_dir), "mmlu")
    cfg = run_config_dict(args, "mmlu")
    cfg["questions_file"] = args.questions
    cfg["limit"] = args.limit
    write_config(run_dir, cfg)

    writer = ResultsWriter(run_dir)
    try:
        summary = mmlu.run(config, questions, args.concurrency, writer, limit=args.limit)
    finally:
        writer.close()

    write_summary(run_dir, summary)
    print_summary(f"MMLU results ({run_dir})", summary)
    return summary


def cmd_code(args, run_dir: pathlib.Path = None) -> dict:
    config = build_chat_config(args)
    tasks = code.load_tasks(args.tasks_dir)

    if run_dir is None:
        run_dir = make_run_dir(pathlib.Path(args.runs_dir), "code")
    cfg = run_config_dict(args, "code")
    cfg["tasks_dir"] = args.tasks_dir
    cfg["verify_timeout"] = args.verify_timeout
    write_config(run_dir, cfg)

    scratch_root = pathlib.Path(args.scratch_dir) if args.scratch_dir else run_dir / "scratch"
    scratch_root.mkdir(parents=True, exist_ok=True)

    writer = ResultsWriter(run_dir)
    try:
        summary = code.run(config, tasks, scratch_root, args.verify_timeout, writer)
    finally:
        writer.close()

    write_summary(run_dir, summary)
    print_summary(f"Code results ({run_dir})", summary)
    return summary


def cmd_ifeval(args, run_dir: pathlib.Path = None) -> dict:
    config = build_chat_config(args)
    cases = ifeval.load_cases(args.cases)

    if run_dir is None:
        run_dir = make_run_dir(pathlib.Path(args.runs_dir), "ifeval")
    cfg = run_config_dict(args, "ifeval")
    cfg["cases_file"] = args.cases
    write_config(run_dir, cfg)

    writer = ResultsWriter(run_dir)
    try:
        summary = ifeval.run(config, cases, writer)
    finally:
        writer.close()

    write_summary(run_dir, summary)
    print_summary(f"IFEval-light results ({run_dir})", summary)
    return summary


def cmd_all(args) -> dict:
    if not (args.questions or args.tasks_dir or args.cases):
        print("error: `all` needs at least one of --questions, --tasks-dir, --cases", file=sys.stderr)
        sys.exit(1)

    run_dir = make_run_dir(pathlib.Path(args.runs_dir), "all")
    results = {}

    if args.questions:
        sub_dir = run_dir / "mmlu"
        sub_dir.mkdir(parents=True)
        results["mmlu"] = cmd_mmlu(args, run_dir=sub_dir)

    if args.tasks_dir:
        sub_dir = run_dir / "code"
        sub_dir.mkdir(parents=True)
        results["code"] = cmd_code(args, run_dir=sub_dir)

    if args.cases:
        sub_dir = run_dir / "ifeval"
        sub_dir.mkdir(parents=True)
        results["ifeval"] = cmd_ifeval(args, run_dir=sub_dir)

    write_summary(run_dir, results)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="localeval", description="Benchmark a local LLM via a llama.cpp OpenAI-compatible endpoint")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    p_mmlu = subparsers.add_parser("mmlu", help="MMLU-style multiple-choice benchmark")
    add_common_args(p_mmlu)
    p_mmlu.add_argument("--questions", required=True, help="Path to the JSON question bank")
    p_mmlu.add_argument("--limit", type=int, default=None, help="Only run the first N questions")
    p_mmlu.set_defaults(func=cmd_mmlu)

    p_code = subparsers.add_parser("code", help="Code generation benchmark")
    add_common_args(p_code)
    p_code.add_argument("--tasks-dir", required=True, help="Directory containing task folders")
    p_code.add_argument("--verify-timeout", type=int, default=120, help="Seconds before a verify run is marked TIMEOUT")
    p_code.add_argument("--scratch-dir", default=None, help="Where generated code is written (default: <run_dir>/scratch)")
    p_code.set_defaults(func=cmd_code)

    p_ifeval = subparsers.add_parser("ifeval", help="IFEval-light instruction-following benchmark")
    add_common_args(p_ifeval)
    p_ifeval.add_argument("--cases", required=True, help="Path to the JSON case file")
    p_ifeval.set_defaults(func=cmd_ifeval)

    p_all = subparsers.add_parser("all", help="Run all applicable modes in one go")
    add_common_args(p_all)
    p_all.add_argument("--questions", default=None, help="Path to the JSON question bank (mmlu)")
    p_all.add_argument("--limit", type=int, default=None, help="Only run the first N questions (mmlu)")
    p_all.add_argument("--tasks-dir", default=None, help="Directory containing task folders (code)")
    p_all.add_argument("--verify-timeout", type=int, default=120, help="Seconds before a verify run is marked TIMEOUT (code)")
    p_all.add_argument("--scratch-dir", default=None, help="Where generated code is written (code)")
    p_all.add_argument("--cases", default=None, help="Path to the JSON case file (ifeval)")
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
