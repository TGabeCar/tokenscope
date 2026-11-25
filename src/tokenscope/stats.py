"""Roll parsed turns up into the numbers the dashboard shows."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from .parser import Turn
from .pricing import Price, cost_usd


@dataclass
class Bucket:
    """Token totals plus estimated cost for any grouping."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0
    turns: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_write_tokens + self.cache_read_tokens

    def add(self, turn: Turn, cost: float) -> None:
        self.input_tokens += turn.input_tokens
        self.output_tokens += turn.output_tokens
        self.cache_write_tokens += turn.cache_write_tokens
        self.cache_read_tokens += turn.cache_read_tokens
        self.cost += cost
        self.turns += 1

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.cost, 4),
            "turns": self.turns,
        }


@dataclass
class SessionStat(Bucket):
    session_id: str = ""
    project: str = ""
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    models: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            session_id=self.session_id,
            project=self.project,
            first_seen=self.first_seen.isoformat() if self.first_seen else None,
            last_seen=self.last_seen.isoformat() if self.last_seen else None,
            models=sorted(self.models),
        )
        return data


@dataclass
class Summary:
    total: Bucket = field(default_factory=Bucket)
    by_model: dict[str, Bucket] = field(default_factory=dict)
    by_project: dict[str, Bucket] = field(default_factory=dict)
    by_day: dict[date, Bucket] = field(default_factory=dict)
    sessions: dict[str, SessionStat] = field(default_factory=dict)
    tools: Counter = field(default_factory=Counter)

    def top_sessions(self, n: int) -> list[SessionStat]:
        return sorted(self.sessions.values(), key=lambda s: s.cost, reverse=True)[:n]

    def to_dict(self, top: int = 10) -> dict:
        return {
            "total": self.total.to_dict(),
            "by_model": {k: v.to_dict() for k, v in sorted(self.by_model.items())},
            "by_project": {k: v.to_dict() for k, v in sorted(self.by_project.items())},
            "by_day": {k.isoformat(): v.to_dict() for k, v in sorted(self.by_day.items())},
            "top_tools": [{"name": n, "calls": c} for n, c in self.tools.most_common(top)],
            "top_sessions": [s.to_dict() for s in self.top_sessions(top)],
            "session_count": len(self.sessions),
        }


def summarize(
    turns: list[Turn],
    since: date | None = None,
    pricing: dict[str, Price] | None = None,
) -> Summary:
    """Aggregate turns. With ``since``, turns before that UTC date (or with no timestamp) are dropped."""
    summary = Summary()
    for turn in turns:
        day = turn.timestamp.date() if turn.timestamp else None
        if since is not None and (day is None or day < since):
            continue

        cost = cost_usd(
            turn.model,
            turn.input_tokens,
            turn.output_tokens,
            turn.cache_write_tokens,
            turn.cache_read_tokens,
            pricing,
        )
        has_usage = (turn.input_tokens + turn.output_tokens + turn.cache_write_tokens + turn.cache_read_tokens) > 0
        summary.tools.update(turn.tools)
        if not has_usage:
            continue

        summary.total.add(turn, cost)
        summary.by_model.setdefault(turn.model or "unknown", Bucket()).add(turn, cost)
        summary.by_project.setdefault(turn.project, Bucket()).add(turn, cost)
        if day is not None:
            summary.by_day.setdefault(day, Bucket()).add(turn, cost)

        key = f"{turn.project}/{turn.session_id}"
        sess = summary.sessions.get(key)
        if sess is None:
            sess = summary.sessions[key] = SessionStat(session_id=turn.session_id, project=turn.project)
        sess.add(turn, cost)
        if turn.model:
            sess.models.add(turn.model)
        if turn.timestamp:
            if sess.first_seen is None or turn.timestamp < sess.first_seen:
                sess.first_seen = turn.timestamp
            if sess.last_seen is None or turn.timestamp > sess.last_seen:
                sess.last_seen = turn.timestamp
    return summary
