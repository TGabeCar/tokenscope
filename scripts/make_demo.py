"""Rebuild docs/demo.svg and docs/demo.txt from the synthetic sample transcripts.

    python scripts/make_demo.py
"""

import io
from pathlib import Path

from rich.console import Console
from rich.terminal_theme import MONOKAI

from tokenscope.cli import main

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "examples" / "sample-transcripts"
DOCS = ROOT / "docs"


def run() -> None:
    DOCS.mkdir(exist_ok=True)
    console = Console(record=True, width=100, force_terminal=True, color_system="truecolor", file=io.StringIO())
    main(["--path", str(SAMPLES), "--top", "5"], console=console)
    console.save_svg(str(DOCS / "demo.svg"), title="tokenscope --path examples/sample-transcripts", theme=MONOKAI, clear=False)
    (DOCS / "demo.txt").write_text(console.export_text(), encoding="utf-8")
    print(f"wrote {DOCS / 'demo.svg'} and {DOCS / 'demo.txt'}")


if __name__ == "__main__":
    run()
