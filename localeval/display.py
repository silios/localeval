"""Rich-based terminal display: a live progress bar while a run executes,
a colored category/constraint breakdown table, and a boxed final summary
panel - styled after tool-eval-bench's terminal UI (boxed panels, colored
bars, star ratings), reused here for localeval's own three modes.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.table import Table
from rich.text import Text

from .reporting import score_fields

console = Console()

CATEGORY_COLORS = [
    "cyan", "blue", "dark_orange3", "red", "green3", "bright_white",
    "magenta", "gold3", "spring_green3", "deep_sky_blue1", "purple", "bright_magenta",
]


def make_progress(description: str) -> Progress:
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )
    progress.description = description
    return progress


def _bar(pct: float, width: int, color: str) -> Text:
    filled = round(width * max(0.0, min(pct, 100.0)) / 100)
    text = Text()
    text.append("█" * filled, style=color)
    text.append("░" * (width - filled), style="grey37")
    return text


def print_breakdown(title: str, rows: list, bar_width: int = 24) -> None:
    """rows: list of (label, score_pct, earned_str) tuples."""
    if not rows:
        return
    table = Table(title=title, title_style="bold", box=None)
    table.add_column("Category")
    table.add_column("Score", justify="right")
    table.add_column("Bar")
    table.add_column("Earned", justify="right")
    for i, (label, pct, earned) in enumerate(rows):
        color = CATEGORY_COLORS[i % len(CATEGORY_COLORS)]
        table.add_row(Text(label, style=color), f"{pct:.0f}%", _bar(pct, bar_width, color), earned)
    console.print(table)


def rating_for(pct: float) -> str:
    if pct >= 90:
        stars, label = 5, "Excellent"
    elif pct >= 75:
        stars, label = 4, "Good"
    elif pct >= 50:
        stars, label = 3, "Fair"
    elif pct >= 25:
        stars, label = 2, "Poor"
    else:
        stars, label = 1, "Very Poor"
    return f"{'★' * stars}{'☆' * (5 - stars)} {label}"


def print_final_panel(mode: str, model: str, earned: int, total: int, counts: dict, elapsed_s: float, report_path, run_total: int = None, latency: dict = None) -> None:
    """`total` is the scored denominator (correct+wrong / pass+fail) used
    for the rating. `run_total` is the full item count attempted,
    including errors and truncated/no_answer items excluded from that
    denominator - when it differs from `total`, this is surfaced
    prominently, never silently. Hiding a run where most items errored
    out behind a clean-looking score is the exact failure mode this tool
    exists to avoid.

    `latency` is an optional dict with p50/p95 TTFT and tokens/sec,
    surfaced when timing data is available.
    """
    pct = (earned / total * 100) if total else 0.0
    errored = counts.get("error", 0)

    lines = [
        f"[bold]Model:[/bold]  {model or 'unknown'}",
        f"[bold]Score:[/bold]  [cyan]{earned} / {total}[/cyan]  (of items that produced a scorable answer)",
        f"[bold]Rating:[/bold] {rating_for(pct)}",
        "",
    ]

    badges = []
    if counts.get("pass"):
        badges.append(f"[green]✅ {counts['pass']} passed[/green]")
    if counts.get("partial"):
        badges.append(f"[yellow]⚠ {counts['partial']} partial[/yellow]")
    if counts.get("fail"):
        badges.append(f"[red]❌ {counts['fail']} failed[/red]")
    if errored:
        badges.append(f"[bold red]⛔ {errored} errored[/bold red]")
    if badges:
        lines.append("   ".join(badges))
        lines.append("")

    if run_total is not None and run_total != total:
        scored_or_partial = total + counts.get("partial", 0)
        lines.append(f"[bold yellow]⚠ Coverage: {scored_or_partial}/{run_total} items produced any response - {errored} never got one.[/bold yellow]")
        lines.append("")

    if latency and latency.get("timed_items"):
        timed = latency["timed_items"]
        lines.append(f"[bold]Latency[/bold] (p50 / p95, {timed} items)")
        lines.append(f"  TTFT:         {latency['ttft_p50_ms']:.0f}ms / {latency['ttft_p95_ms']:.0f}ms")
        lines.append(f"  tokens/sec:   {latency['tps_p50']:.1f} / {latency['tps_p95']:.1f}")
        lines.append("")

    lines.append(f"Completed in {elapsed_s:.1f}s   |   localeval {mode}")
    lines.append(f"Report: {report_path}")

    incomplete = errored > 0
    title = "⚠️  Benchmark Incomplete" if incomplete else "🏆 Benchmark Complete"
    border_style = "yellow" if incomplete else "red"
    panel = Panel("\n".join(lines), title=title, border_style=border_style, expand=False)
    console.print(panel)


def print_global_panel(entries: list, elapsed_s: float, report_path) -> None:
    """entries: list of {"mode", "model", "summary", "report_path"} dicts,
    one per mode run under `localeval all`. Aggregates them into one
    combined score/rating/coverage view across every mode that ran,
    same honesty rules as print_final_panel - errors are never hidden.
    """
    all_fields = [(e["mode"], score_fields(e["mode"], e["summary"])) for e in entries]
    overall_earned = sum(f["earned"] for _, f in all_fields)
    overall_total = sum(f["total"] for _, f in all_fields)
    overall_run_total = sum(f["run_total"] for _, f in all_fields)
    overall_counts = {"pass": 0, "partial": 0, "fail": 0, "error": 0}
    for _, f in all_fields:
        for k in overall_counts:
            overall_counts[k] += f["counts"].get(k, 0)

    pct = (overall_earned / overall_total * 100) if overall_total else 0.0
    errored = overall_counts["error"]

    lines = [
        f"[bold]Modes:[/bold]  {', '.join(mode for mode, _ in all_fields)}",
        f"[bold]Overall Score:[/bold]  [cyan]{overall_earned} / {overall_total}[/cyan]",
        f"[bold]Overall Rating:[/bold] {rating_for(pct)}",
        "",
    ]
    for mode, f in all_fields:
        sub_pct = (f["earned"] / f["total"] * 100) if f["total"] else 0.0
        lines.append(f"  {mode}: {f['earned']}/{f['total']} ({sub_pct:.0f}%) - {rating_for(sub_pct)}")
    lines.append("")

    badges = []
    if overall_counts["pass"]:
        badges.append(f"[green]✅ {overall_counts['pass']} passed[/green]")
    if overall_counts["partial"]:
        badges.append(f"[yellow]⚠ {overall_counts['partial']} partial[/yellow]")
    if overall_counts["fail"]:
        badges.append(f"[red]❌ {overall_counts['fail']} failed[/red]")
    if errored:
        badges.append(f"[bold red]⛔ {errored} errored[/bold red]")
    if badges:
        lines.append("   ".join(badges))
        lines.append("")

    if overall_run_total != overall_total:
        scored_or_partial = overall_total + overall_counts["partial"]
        lines.append(f"[bold yellow]⚠ Coverage: {scored_or_partial}/{overall_run_total} items produced any response - {errored} never got one.[/bold yellow]")
        lines.append("")

    lines.append(f"Completed in {elapsed_s:.1f}s   |   localeval all")
    lines.append(f"Global report: {report_path}")

    incomplete = errored > 0
    title = "⚠️  All Benchmarks Incomplete" if incomplete else "🏆 All Benchmarks Complete"
    border_style = "yellow" if incomplete else "red"
    panel = Panel("\n".join(lines), title=title, border_style=border_style, expand=False)
    console.print(panel)


def _delta_str(delta, suffix: str = "") -> str:
    """Format a delta value with color: green for positive (improvement),
    red for negative (regression), dim for zero."""
    if isinstance(delta, str) or delta is None:
        return "-"
    if delta > 0:
        return f"[green]+{delta:.1f}{suffix}[/green]"
    elif delta < 0:
        return f"[red]{delta:.1f}{suffix}[/red]"
    return f"[dim]{delta:.1f}{suffix}[/dim]"


def print_compare(result: dict, model_a: str = "", model_b: str = "") -> None:
    """Side-by-side comparison of two runs, rendered as Rich tables.

    result: the dict returned by compare.diff_summaries()
    model_a: model name for the baseline (run 1)
    model_b: model name for the comparison (run 2)
    """
    mode = result["mode"]
    ov = result["overall"]
    group_label = "Constraints" if mode == "ifeval" else "Categories"
    groups = result.get("constraints") or result.get("categories") or {}

    # --- Overall comparison ---
    lines = [
        f"[bold]Mode:[/bold] {mode}",
        f"[bold]A (baseline):[/bold] {model_a or 'run 1'}",
        f"[bold]B (compare):[/bold]  {model_b or 'run 2'}",
        "",
        f"[bold]Score:[/bold]  [cyan]{ov['earned_a']}/{ov['total_a']}[/cyan]  →  [cyan]{ov['earned_b']}/{ov['total_b']}[/cyan]",
        f"[bold]Δ:[/bold]      {_delta_str(ov['earned_delta'], '')} items  ({_delta_str(ov['pct_delta'], ' pp')})",
    ]

    if ov["errors_a"] or ov["errors_b"]:
        lines.append(f"[bold]Errors:[/bold] {ov['errors_a']} → {ov['errors_b']}")

    lines.append("")
    panel = Panel("\n".join(lines), title="📊 Compare Runs", border_style="blue", expand=False)
    console.print(panel)

    # --- Per-category / per-constraint table ---
    if groups:
        table = Table(title=f"{group_label} Breakdown", title_style="bold", box=None)
        table.add_column(group_label[:-1])  # singular
        table.add_column("A", justify="right")
        table.add_column("B", justify="right")
        table.add_column("Δ", justify="right")
        for name, g in groups.items():
            color = CATEGORY_COLORS[hash(name) % len(CATEGORY_COLORS)]
            name_cell = Text(name, style=color)
            if isinstance(g["pct_a"], str):
                a_cell, b_cell, d_cell = "-", f"{g['pct_b']:.0f}%", "-"
            elif isinstance(g["pct_b"], str):
                a_cell, b_cell, d_cell = f"{g['pct_a']:.0f}%", "-", "-"
            else:
                a_cell = f"{g['pct_a']:.0f}%"
                b_cell = f"{g['pct_b']:.0f}%"
                d_cell = _delta_str(g["pct_delta"], " pp")
            table.add_row(name_cell, a_cell, b_cell, d_cell)
        console.print(table)
        console.print("")

    # --- Latency comparison ---
    latency = result.get("latency") or {}
    if latency:
        table = Table(title="Latency (p50 / p95)", title_style="bold", box=None)
        table.add_column("Metric")
        table.add_column("A", justify="right")
        table.add_column("B", justify="right")
        table.add_column("Δ", justify="right")
        for label, field_a, field_b, field_d, suffix in [
            ("TTFT p50", "ttft_p50_ms_a", "ttft_p50_ms_b", "ttft_p50_delta_ms", "ms"),
            ("TTFT p95", "ttft_p95_ms_a", "ttft_p95_ms_b", "ttft_p95_delta_ms", "ms"),
            ("tok/s p50", "tps_p50_a", "tps_p50_b", "tps_p50_delta", ""),
            ("tok/s p95", "tps_p95_a", "tps_p95_b", "tps_p95_delta", ""),
        ]:
            if field_a in latency and field_b in latency:
                a_val = f"{latency[field_a]:.0f}{suffix}" if suffix else f"{latency[field_a]:.1f}"
                b_val = f"{latency[field_b]:.0f}{suffix}" if suffix else f"{latency[field_b]:.1f}"
                # For TTFT, negative delta = faster = good (= green)
                # For tok/s, positive delta = faster = good (= green)
                delta_val = latency.get(field_d)
                if delta_val is not None:
                    is_good = (delta_val < 0 and "ttft" in field_d) or (delta_val > 0 and "tps" in field_d)
                    if is_good:
                        d_text = f"[green]{delta_val:+.1f}{suffix}[/green]"
                    elif delta_val == 0:
                        d_text = f"[dim]{delta_val:.1f}{suffix}[/dim]"
                    else:
                        d_text = f"[red]{delta_val:+.1f}{suffix}[/red]"
                else:
                    d_text = "-"
                table.add_row(label, a_val, b_val, d_text)
        console.print(table)


def print_list_runs(runs: list) -> None:
    """Print a table of past runs with mode, model, timestamp, score, rating.

    runs: list of dicts as returned by __main__.list_runs().
    """
    table = Table(title="Past Runs", title_style="bold", box=None)
    table.add_column("Mode")
    table.add_column("Model")
    table.add_column("Timestamp")
    table.add_column("Score", justify="right")
    table.add_column("Rating")
    for r in runs:
        score = f"{r['earned']}/{r['total']}"
        if r["errors"]:
            score += f" [red]⛔{r['errors']}[/red]"
        table.add_row(
            r["mode"],
            r["model"] or "-",
            r["timestamp"],
            score,
            r["rating"],
        )
    console.print(table)
    console.print(f"\n{runs[0]['run_dir'].rsplit('/', 3)[0]}/{runs[0]['mode']}/")


def print_bench_results(results: list, model: str = "", depths: list = None) -> None:
    """Print throughput benchmark results as a Rich table.

    results: list of dicts from bench.run_benchmark()
    """
    panel = Panel(
        f"[bold]Model:[/bold] {model or 'unknown'}\n"
        f"[bold]Depths:[/bold] {depths or []}\n"
        f"[bold]Runs:[/bold] {len(results)} total",
        title="⚡ Throughput Benchmark",
        border_style="purple",
    )
    console.print(panel)
    console.print("")

    table = Table(title="Bench Results", title_style="bold", box=None)
    table.add_column("Depth")
    table.add_column("pp t/s", justify="right")
    table.add_column("tg t/s", justify="right")
    table.add_column("Total (ms)", justify="right")
    table.add_column("Tokens", justify="right")

    for r in results:
        if not r.get("ok"):
            table.add_row(
                f"d{r['depth']}",
                "-", "-", "-",
                f"[red]{r.get('error', 'error')}[/red]",
            )
        else:
            depth_label = f"d{r['depth']}"
            pp = f"{r['pp_tokens_per_sec']:,.0f}"
            tg = f"{r['tg_tokens_per_sec']:,.0f}"
            total = f"{r['total_ms']:,.0f}"
            tokens = f"{r['pp_tokens']}+{r['tg_tokens']}"
            table.add_row(depth_label, pp, tg, total, tokens)

    console.print(table)
