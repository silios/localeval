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
