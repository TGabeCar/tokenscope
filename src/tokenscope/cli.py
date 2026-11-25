"""Command-line entry point: ``tokenscope``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from rich.console import Console

from . import __version__
from .parser import parse_path
from .pricing import load_pricing
from .render import render
from .stats import summarize

DEFAULT_PATH = Path("~/.claude/projects")


def _since(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from exc


def _top(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("--top must be at least 1")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tokenscope",
        description="A token-usage and cost dashboard for Claude Code session transcripts.",
    )
    p.add_argument("--path", default=str(DEFAULT_PATH), help="transcript file or folder (default: ~/.claude/projects)")
    p.add_argument("--since", type=_since, help="only count turns on or after this UTC date (YYYY-MM-DD)")
    p.add_argument("--top", type=_top, default=5, help="rows to show in the top-N tables (default: 5)")
    p.add_argument("--json", action="store_true", help="print machine-readable JSON instead of the dashboard")
    p.add_argument("--pricing", help="JSON file of model prices that overrides the built-in estimates")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _utf8_streams() -> None:
    """Redirected output on Windows defaults to a legacy code page; the dashboard needs UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):  # pragma: no cover
                pass


def main(argv: list[str] | None = None, console: Console | None = None) -> int:
    args = build_parser().parse_args(argv)
    _utf8_streams()
    err = Console(stderr=True)

    path = Path(args.path).expanduser()
    if not path.exists():
        err.print(f"[red]Path not found:[/] {path}")
        return 2

    pricing = None
    if args.pricing:
        try:
            pricing = load_pricing(args.pricing)
        except (OSError, ValueError) as exc:
            err.print(f"[red]Could not read pricing file:[/] {exc}")
            return 2

    result = parse_path(path)
    summary = summarize(result.turns, since=args.since, pricing=pricing)

    if args.json:
        payload = summary.to_dict(top=args.top)
        payload["meta"] = {
            "files": result.files,
            "lines": result.lines,
            "skipped_lines": result.skipped,
            "since": args.since.isoformat() if args.since else None,
            "cost_note": "estimates only; see tokenscope/pricing.py",
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0

    source = f"{result.files} transcript(s) · {result.lines} lines · {result.skipped} skipped"
    if args.since:
        source += f" · since {args.since.isoformat()}"
    render(summary, console=console, top=args.top, source=source)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
