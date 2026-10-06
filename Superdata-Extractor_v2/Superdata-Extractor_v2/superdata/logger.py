"""Rich-based logging helpers for Superdata Extractor."""

from __future__ import annotations

import logging
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.theme import Theme

CUSTOM_THEME = Theme(
    {
        "info": "cyan",
        "success": "green bold",
        "warning": "yellow",
        "error": "red bold",
        "step": "magenta",
    }
)

console = Console(theme=CUSTOM_THEME, force_terminal=True)


def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    return logging.getLogger("superdata")


def print_banner() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]Superdata Extractor[/bold cyan]\n"
            "[dim]Frontend intelligence -> predictive backend blueprint[/dim]",
            border_style="cyan",
        )
    )


def print_extraction_summary(summary: dict) -> None:
    table = Table(title="Extraction Summary", show_header=True, header_style="bold magenta")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right", style="green")

    counts = summary.get("counts", {})
    for key, value in counts.items():
        table.add_row(key.replace("_", " ").title(), str(value))

    console.print(table)

    warnings = summary.get("warnings", [])
    if warnings:
        console.print(f"\n[warning]Warnings ({len(warnings)}):[/warning]")
        for w in warnings[:10]:
            console.print(f"  [warning]-[/warning] {w}")
        if len(warnings) > 10:
            console.print(f"  [dim]… and {len(warnings) - 10} more[/dim]")


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def log_folder_created(path: str, label: Optional[str] = None) -> None:
    name = label or path
    console.print(f"[success][OK][/success] {name} -> [dim]{path}[/dim]")
