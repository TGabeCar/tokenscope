"""Draw the terminal dashboard with rich."""

from __future__ import annotations

from datetime import date, timedelta

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .stats import Bucket, Summary

SPARK_CHARS = " ▁▂▃▄▅▆▇█"
BAR_WIDTH = 28
WIDE = 96  # at or above this many columns, projects and tools sit side by side


def human(n: float) -> str:
    """1234567 -> '1.23M'."""
    n = float(n)
    for unit, size in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(n) >= size:
            return f"{n / size:.2f}{unit}"
    return f"{int(n)}"


def money(x: float) -> str:
    return f"${x:,.2f}"


def sparkline(values: list[float]) -> str:
    """Unicode sparkline, one character per value."""
    if not values:
        return ""
    top = max(values)
    if top <= 0:
        return SPARK_CHARS[1] * len(values)
    steps = len(SPARK_CHARS) - 1
    return "".join(SPARK_CHARS[max(1, round(v / top * steps))] if v > 0 else SPARK_CHARS[0] for v in values)


def bar(value: float, top: float, width: int = BAR_WIDTH) -> str:
    if top <= 0 or value <= 0:
        return ""
    filled = value / top * width
    full = int(filled)
    return "█" * full + ("▌" if filled - full >= 0.5 else "")


def fill_days(by_day: dict[date, Bucket]) -> list[tuple[date, Bucket]]:
    """Every day from first to last, with empty buckets for quiet days."""
    if not by_day:
        return []
    start, end = min(by_day), max(by_day)
    out = []
    d = start
    while d <= end:
        out.append((d, by_day.get(d, Bucket())))
        d += timedelta(days=1)
    return out


def _stat(label: str, value: str, style: str) -> Panel:
    return Panel(
        Text.assemble((value, f"bold {style}"), "\n", (label, "dim")),
        box=box.ROUNDED,
        border_style=style,
        padding=(0, 1),
    )


def build_dashboard(summary: Summary, top: int = 5, source: str = "", width: int = 100) -> Group:
    t = summary.total
    days = fill_days(summary.by_day)

    header = Text.assemble(
        ("tokenscope", "bold magenta"),
        ("  ·  where did all the tokens go?", "italic dim"),
    )
    if source:
        header.append(f"\n{source}", style="dim")

    cards = Table.grid(expand=True, padding=(0, 1))
    for _ in range(6):
        cards.add_column(ratio=1)
    cards.add_row(
        *[
            _stat("input", human(t.input_tokens), "cyan"),
            _stat("output", human(t.output_tokens), "green"),
            _stat("cache wr", human(t.cache_write_tokens), "yellow"),
            _stat("cache rd", human(t.cache_read_tokens), "blue"),
            _stat("est cost", money(t.cost), "magenta"),
            _stat("sessions", str(len(summary.sessions)), "white"),
        ]
    )

    models = Table(box=box.SIMPLE_HEAVY, expand=True, title="By model", title_style="bold")
    models.add_column("model", style="bold")
    models.add_column("turns", justify="right")
    models.add_column("input", justify="right", style="cyan")
    models.add_column("output", justify="right", style="green")
    models.add_column("cache r/w", justify="right", style="blue")
    models.add_column("est. cost", justify="right", style="magenta")
    for name, b in sorted(summary.by_model.items(), key=lambda kv: kv[1].cost, reverse=True):
        models.add_row(
            name,
            str(b.turns),
            human(b.input_tokens),
            human(b.output_tokens),
            f"{human(b.cache_read_tokens)} / {human(b.cache_write_tokens)}",
            money(b.cost),
        )

    projects = Table(box=box.SIMPLE_HEAVY, expand=True, title="By project", title_style="bold")
    projects.add_column("project", style="bold")
    projects.add_column("tokens", justify="right")
    projects.add_column("est. cost", justify="right", style="magenta")
    projects.add_column("share", ratio=1, no_wrap=True, overflow="crop")
    top_proj = max((b.cost for b in summary.by_project.values()), default=0)
    for name, b in sorted(summary.by_project.items(), key=lambda kv: kv[1].cost, reverse=True):
        projects.add_row(name, human(b.total_tokens), money(b.cost), Text(bar(b.cost, top_proj, 20), style="magenta"))

    daily = Table(box=box.SIMPLE_HEAVY, expand=True, title="By day (UTC)", title_style="bold")
    daily.add_column("day")
    daily.add_column("tokens", justify="right")
    daily.add_column("est. cost", justify="right", style="magenta")
    daily.add_column("", ratio=1)
    top_day = max((b.cost for _, b in days), default=0)
    for d, b in days:
        daily.add_row(d.strftime("%a %m-%d"), human(b.total_tokens), money(b.cost), Text(bar(b.cost, top_day), style="cyan"))
    spark = Text.assemble(("cost trend  ", "dim"), (sparkline([b.cost for _, b in days]), "bold cyan"))

    tools = Table(box=box.SIMPLE_HEAVY, expand=True, title=f"Top {top} tools", title_style="bold")
    tools.add_column("tool", style="bold")
    tools.add_column("calls", justify="right")
    tools.add_column("", ratio=1, no_wrap=True, overflow="crop")
    common = summary.tools.most_common(top)
    top_tool = common[0][1] if common else 0
    for name, count in common:
        tools.add_row(name, str(count), Text(bar(count, top_tool, 16), style="green"))

    sessions = Table(box=box.SIMPLE_HEAVY, expand=True, title=f"Top {top} most expensive sessions", title_style="bold")
    sessions.add_column("session")
    sessions.add_column("project", style="bold")
    sessions.add_column("started (UTC)")
    sessions.add_column("turns", justify="right")
    sessions.add_column("tokens", justify="right")
    sessions.add_column("est. cost", justify="right", style="magenta")
    for s in summary.top_sessions(top):
        sessions.add_row(
            s.session_id[:8],
            s.project,
            s.first_seen.strftime("%Y-%m-%d %H:%M") if s.first_seen else "-",
            str(s.turns),
            human(s.total_tokens),
            money(s.cost),
        )

    if width >= WIDE:
        middle = Table.grid(expand=True, padding=(0, 2))
        middle.add_column(ratio=3)
        middle.add_column(ratio=2)
        middle.add_row(projects, tools)
    else:
        middle = Group(projects, tools)

    footer = Text(
        "Costs are estimates from the pricing table in tokenscope/pricing.py (override with --pricing).",
        style="dim italic",
    )

    return Group(
        Panel(header, box=box.HEAVY, border_style="magenta"),
        cards,
        models,
        middle,
        daily,
        spark,
        sessions,
        footer,
    )


def render(summary: Summary, console: Console | None = None, top: int = 5, source: str = "") -> None:
    console = console or Console()
    if not summary.total.turns and not summary.tools:
        console.print("[yellow]No usage found.[/] Point me at transcripts with [bold]--path[/].")
        return
    console.print(build_dashboard(summary, top=top, source=source, width=console.width))
