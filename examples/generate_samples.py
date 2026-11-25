"""Regenerate the synthetic transcripts in examples/sample-transcripts/.

Everything here is invented: projects, prompts, session ids and numbers.
The output is deterministic (fixed random seed), so tests can rely on it.

    python examples/generate_samples.py
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent / "sample-transcripts"
rng = random.Random(42)

PROJECTS = {
    "demo-webapp": {
        "models": ["claude-sonnet-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
        "tools": ["Read", "Edit", "Bash", "Grep", "Write"],
        "prompts": [
            "Add a dark-mode toggle to the settings page",
            "Why does the login form submit twice?",
            "Write tests for the cart total calculation",
        ],
        "sessions": [(datetime(2026, 11, 2, 9, 15), 28), (datetime(2026, 11, 5, 14, 40), 41), (datetime(2026, 11, 11, 10, 5), 22)],
    },
    "data-pipeline": {
        "models": ["claude-opus-5-5", "claude-opus-5-5", "claude-haiku-5-5"],
        "tools": ["Bash", "Read", "Glob", "Edit", "TodoWrite"],
        "prompts": [
            "Make the nightly CSV import idempotent",
            "Profile the slow join in the orders step",
        ],
        "sessions": [(datetime(2026, 11, 3, 16, 0), 35), (datetime(2026, 11, 8, 8, 30), 52)],
    },
    "cli-toolkit": {
        "models": ["claude-haiku-5-5", "claude-sonnet-5-5"],
        "tools": ["Read", "Edit", "Bash", "WebFetch"],
        "prompts": [
            "Add a --dry-run flag to the sync command",
            "Tidy up the help text",
        ],
        "sessions": [(datetime(2026, 11, 6, 19, 20), 18), (datetime(2026, 11, 9, 11, 45), 24)],
    },
}


def iso(ts: datetime) -> str:
    return ts.replace(tzinfo=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def session_lines(project: str, spec: dict, start: datetime, turns: int, prompt: str) -> list[str]:
    sid = str(uuid.UUID(int=rng.getrandbits(128), version=4))
    ts = start
    lines: list[str] = []
    model = rng.choice(spec["models"])
    lines.append(json.dumps({
        "type": "user", "sessionId": sid, "timestamp": iso(ts), "cwd": f"/home/dev/{project}",
        "message": {"role": "user", "content": prompt},
    }))
    cache = 0
    for i in range(turns):
        ts += timedelta(seconds=rng.randint(20, 240))
        cache_write = rng.randint(1_500, 9_000) if i == 0 or rng.random() < 0.2 else rng.randint(0, 800)
        cache_read = cache
        cache += cache_write
        usage = {
            "input_tokens": rng.randint(3, 60),
            "output_tokens": rng.randint(120, 2_400),
            "cache_creation_input_tokens": cache_write,
            "cache_read_input_tokens": cache_read,
        }
        content: list[dict] = [{"type": "text", "text": "On it. Let me look at the relevant files first."}]
        n_tools = rng.choice([0, 1, 1, 2, 3])
        for _ in range(n_tools):
            content.append({"type": "tool_use", "id": f"toolu_{rng.getrandbits(48):012x}", "name": rng.choice(spec["tools"]), "input": {}})
        msg_id = f"msg_{rng.getrandbits(64):016x}"
        record = {
            "type": "assistant", "sessionId": sid, "timestamp": iso(ts),
            "message": {"id": msg_id, "role": "assistant", "model": model, "usage": usage, "content": content},
        }
        lines.append(json.dumps(record))
        if i == 1:
            # Same message written again as a second line (Claude Code does this per content block).
            extra = dict(record, message=dict(record["message"], content=[{"type": "tool_use", "id": "toolu_split", "name": "Read", "input": {}}]))
            lines.append(json.dumps(extra))
        if n_tools:
            lines.append(json.dumps({
                "type": "user", "sessionId": sid, "timestamp": iso(ts + timedelta(seconds=2)),
                "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_x", "content": "ok"}]},
            }))
    return lines


def main() -> None:
    for project, spec in PROJECTS.items():
        folder = OUT / project
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.jsonl"):
            old.unlink()
        for (start, turns), prompt in zip(spec["sessions"], spec["prompts"] * 2):
            lines = session_lines(project, spec, start, turns, prompt)
            sid = json.loads(lines[0])["sessionId"]
            if project == "demo-webapp" and start.day == 5:
                lines.insert(3, '{"type": "assistant", "message": {"usage": BROKEN')  # malformed on purpose
                lines.insert(4, '{"type": "summary", "summary": "Dark mode toggle"}')
            (folder / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote samples to {OUT}")


if __name__ == "__main__":
    main()
