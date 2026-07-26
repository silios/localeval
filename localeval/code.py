"""Code-generation benchmark mode.

Input: a directory of task folders. Each task folder contains:
  task.md or task.txt   - the problem description (required)
  verify.sh or verify.py - a script that exits 0 on pass, nonzero on fail
                            (required); run with the scratch dir as cwd
  filename.txt            - optional, one line with the filename the
                            generated code should be written as (default:
                            solution.py)

The model is given the task description in a single turn and asked to
respond with the complete solution in a single fenced code block. The
code is written to disk and verify.sh/verify.py is run against it with a
configurable timeout; the process exit code is the verdict.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

from .client import ChatConfig, chat_completion

CODE_FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)

SYSTEM_PROMPT = (
    "You are a code generation assistant. Read the task description and "
    "respond with a complete, self-contained solution as a single fenced "
    "code block. Do not split the solution across multiple code blocks."
)

DEFAULT_FILENAME = "solution.py"


def load_tasks(tasks_dir: str) -> list:
    tasks = []
    root = pathlib.Path(tasks_dir)
    for task_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        task_file = task_dir / "task.md"
        if not task_file.exists():
            task_file = task_dir / "task.txt"
        if not task_file.exists():
            continue

        verify_file = task_dir / "verify.sh"
        if not verify_file.exists():
            verify_file = task_dir / "verify.py"
        if not verify_file.exists():
            continue

        filename_hint = task_dir / "filename.txt"
        filename = filename_hint.read_text().strip() if filename_hint.exists() else DEFAULT_FILENAME

        tasks.append(
            {
                "name": task_dir.name,
                "description": task_file.read_text(),
                "verify_path": verify_file,
                "filename": filename,
            }
        )
    return tasks


def extract_code(text: str):
    """Return the code from the first fenced block, or None if absent."""
    match = CODE_FENCE_RE.search(text)
    if not match:
        return None
    return match.group(1)


def run_verify(verify_path: pathlib.Path, scratch_dir: pathlib.Path, timeout: int):
    if verify_path.name.endswith(".py"):
        cmd = ["python3", str(verify_path.resolve())]
    else:
        cmd = ["bash", str(verify_path.resolve())]
    try:
        proc = subprocess.run(
            cmd,
            cwd=scratch_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "status": "pass" if proc.returncode == 0 else "fail",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }


def run_task(config: ChatConfig, task: dict, scratch_root: pathlib.Path, verify_timeout: int) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task["description"]},
    ]
    request = {"messages": messages, "max_tokens": config.max_tokens, "model": config.model}

    result = chat_completion(config, messages)
    if not result.ok:
        return {
            "name": task["name"],
            "status": "error",
            "error": result.error,
            "request": request,
        }

    scratch_dir = scratch_root / task["name"]
    scratch_dir.mkdir(parents=True, exist_ok=True)

    code = extract_code(result.content)
    if code is None:
        return {
            "name": task["name"],
            "status": "no_code_block",
            "finish_reason": result.finish_reason,
            "request": request,
            "raw_response": result.raw_response,
            "response_text": result.content,
        }

    solution_path = scratch_dir / task["filename"]
    solution_path.write_text(code)

    verify_result = run_verify(task["verify_path"], scratch_dir, verify_timeout)

    return {
        "name": task["name"],
        "status": verify_result["status"],
        "finish_reason": result.finish_reason,
        "request": request,
        "raw_response": result.raw_response,
        "response_text": result.content,
        "solution_path": str(solution_path),
        "verify_returncode": verify_result["returncode"],
        "verify_stdout": verify_result["stdout"],
        "verify_stderr": verify_result["stderr"],
    }


def run(config: ChatConfig, tasks: list, scratch_root: pathlib.Path, verify_timeout: int, results_writer) -> dict:
    results = []
    for task in tasks:
        r = run_task(config, task, scratch_root, verify_timeout)
        results.append(r)
        results_writer.write(r)

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    timeout = sum(1 for r in results if r["status"] == "timeout")
    no_code = sum(1 for r in results if r["status"] == "no_code_block")
    errors = sum(1 for r in results if r["status"] == "error")

    denominator = passed + failed
    pass_rate = (passed / denominator * 100) if denominator else 0.0

    summary = {
        "total": len(results),
        "pass": passed,
        "fail": failed,
        "timeout": timeout,
        "no_code_block": no_code,
        "error": errors,
        "pass_rate_pct": round(pass_rate, 1),
    }
    return summary, results
