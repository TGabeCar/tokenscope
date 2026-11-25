"""Model pricing used for cost *estimates*.

ESTIMATE ONLY. These are list prices in US dollars per million tokens, copied
by hand into this file. Vendors change prices, discounts and plans differ, and
a Claude Code subscription is not billed per token at all. Treat every dollar
figure tokenscope prints as a rough guide, not an invoice.

To change a price, edit ``PRICING`` below, or pass ``--pricing my-prices.json``
on the command line with a file shaped like::

    {
      "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": 0.2}
    }

Model names are matched by longest prefix, so ``claude-sonnet-5-5`` also covers
a dated variant such as ``claude-sonnet-5-5-20260101``. Unknown models fall
back to ``DEFAULT_PRICE``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Price:
    """USD per one million tokens."""

    input: float
    output: float
    cache_write: float
    cache_read: float


# Edit me. USD per 1M tokens. Cache writes assume the 5-minute cache (1.25x input).
PRICING: dict[str, Price] = {
    "claude-fable-5-2": Price(input=8.00, output=40.00, cache_write=10.00, cache_read=0.20),
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_write=5.00, cache_read=0.20),
    "claude-opus-5": Price(input=5.00, output=25.00, cache_write=6.25, cache_read=0.50),
    "claude-opus-4": Price(input=5.00, output=25.00, cache_write=6.25, cache_read=0.50),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_write=2.50, cache_read=0.10),
    "claude-sonnet-5": Price(input=2.00, output=10.00, cache_write=2.50, cache_read=0.20),
    "claude-sonnet-4": Price(input=3.00, output=15.00, cache_write=3.75, cache_read=0.30),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_write=0.125, cache_read=0.01),
    "claude-haiku-4": Price(input=1.00, output=5.00, cache_write=1.25, cache_read=0.10),
}

# Used when a model name matches nothing above.
DEFAULT_PRICE = Price(input=3.00, output=15.00, cache_write=3.75, cache_read=0.30)


def price_for(model: str | None, table: dict[str, Price] | None = None) -> Price:
    """Return the price for ``model`` using longest-prefix match."""
    table = PRICING if table is None else table
    if not model:
        return DEFAULT_PRICE
    best = None
    for prefix in table:
        if model.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return table[best] if best else DEFAULT_PRICE


def cost_usd(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
    table: dict[str, Price] | None = None,
) -> float:
    """Estimated cost in USD for one bundle of usage."""
    p = price_for(model, table)
    return (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_write_tokens * p.cache_write
        + cache_read_tokens * p.cache_read
    ) / 1_000_000


def load_pricing(path: str | Path) -> dict[str, Price]:
    """Merge a JSON pricing file over the built-in table and return the result."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("pricing file must be a JSON object of model -> prices")
    table = dict(PRICING)
    for model, fields in raw.items():
        if not isinstance(fields, dict):
            raise ValueError(f"pricing for {model!r} must be an object")
        base = table.get(model, DEFAULT_PRICE)
        table[model] = Price(
            input=float(fields.get("input", base.input)),
            output=float(fields.get("output", base.output)),
            cache_write=float(fields.get("cache_write", base.cache_write)),
            cache_read=float(fields.get("cache_read", base.cache_read)),
        )
    return table
