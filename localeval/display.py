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


def print_final_panel(mode: str, model: str, earned: int, total: int, counts: dict, elapsed_s: float, report_path) -> None:
    pct = (earned / total * 100) if total else 0.0

    lines = [
        f"[bold]Model:[/bold]  {model or 'unknown'}",
        f"[bold]Score:[/bold]  [cyan]{earned} / {total}[/cyan]",
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
    if badges:
        lines.append("   ".join(badges))
        lines.append("")

    lines.append(f"Completed in {elapsed_s:.1f}s   |   localeval {mode}")
    lines.append(f"Report: {report_path}")

    panel = Panel("\n".join(lines), title="🏆 Benchmark Complete", border_style="red", expand=False)
    console.print(panel)
