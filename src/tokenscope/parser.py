"""Tolerant reader for Claude Code session transcripts (JSON Lines).

Assumed shape of one line (anything missing is simply skipped)::

    {
      "type": "assistant",
      "sessionId": "…",
      "timestamp": "2026-11-03T14:22:05.123Z",
      "message": {
        "id": "msg_…",
        "model": "claude-sonnet-5-5",
        "usage": {
          "input_tokens": 12,
          "output_tokens": 340,
          "cache_creation_input_tokens": 2048,
          "cache_read_input_tokens": 18000
        },
        "content": [{"type": "tool_use", "name": "Read", "input": {}}]
      }
    }

The project is the name of the folder that holds the ``.jsonl`` file.

Claude Code can write one assistant message across several lines (one per
content block), each repeating the same ``message.id`` and ``usage``. Usage is
therefore counted once per ``message.id``; tool calls are counted on every line.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator


@dataclass
class Turn:
    """One assistant turn's worth of usage."""

    project: str
    session_id: str
    timestamp: datetime | None
    model: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    tools: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    turns: list[Turn] = field(default_factory=list)
    files: int = 0
    lines: int = 0
    skipped: int = 0


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return 0


def parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp (``Z`` suffix allowed). Returns aware UTC or None."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def find_transcripts(path: str | Path) -> list[Path]:
    """Return every ``.jsonl`` file at ``path`` (a file or a directory, searched recursively)."""
    p = Path(path).expanduser()
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(f for f in p.rglob("*.jsonl") if f.is_file())
    return []


def _turn_from_record(record: dict, project: str, fallback_session: str) -> tuple[Turn, str | None] | None:
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    if record.get("type") not in (None, "assistant") and message.get("role") != "assistant":
        return None

    usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
    content = message.get("content")
    tools: list[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                name = item.get("name")
                if isinstance(name, str) and name:
                    tools.append(name)

    if not usage and not tools:
        return None

    session = record.get("sessionId")
    model = message.get("model")
    turn = Turn(
        project=project,
        session_id=session if isinstance(session, str) and session else fallback_session,
        timestamp=parse_timestamp(record.get("timestamp")),
        model=model if isinstance(model, str) and model else None,
        input_tokens=_as_int(usage.get("input_tokens")),
        output_tokens=_as_int(usage.get("output_tokens")),
        cache_write_tokens=_as_int(usage.get("cache_creation_input_tokens")),
        cache_read_tokens=_as_int(usage.get("cache_read_input_tokens")),
        tools=tools,
    )
    msg_id = message.get("id")
    return turn, msg_id if isinstance(msg_id, str) and msg_id else None


def iter_lines(lines: Iterable[str], project: str, fallback_session: str, result: ParseResult) -> Iterator[Turn]:
    """Yield turns from raw JSONL lines, updating counters on ``result``."""
    seen_ids: set[str] = set()
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        result.lines += 1
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            result.skipped += 1
            continue
        if not isinstance(record, dict):
            result.skipped += 1
            continue
        parsed = _turn_from_record(record, project, fallback_session)
        if parsed is None:
            continue
        turn, msg_id = parsed
        if msg_id is not None:
            if msg_id in seen_ids:
                # Same message split over several lines: keep its tool calls, drop repeated usage.
                turn.input_tokens = turn.output_tokens = 0
                turn.cache_write_tokens = turn.cache_read_tokens = 0
            seen_ids.add(msg_id)
        yield turn


def parse_path(path: str | Path) -> ParseResult:
    """Parse every transcript under ``path``."""
    result = ParseResult()
    for file in find_transcripts(path):
        result.files += 1
        project = file.parent.name or "unknown"
        try:
            with file.open("r", encoding="utf-8", errors="replace") as fh:
                result.turns.extend(iter_lines(fh, project, file.stem, result))
        except OSError:
            result.skipped += 1
    return result
