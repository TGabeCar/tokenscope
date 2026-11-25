import json

import pytest

from tokenscope.pricing import DEFAULT_PRICE, PRICING, cost_usd, load_pricing, price_for


def test_longest_prefix_wins():
    assert price_for("claude-sonnet-5-5-20260101") is PRICING["claude-sonnet-5-5"]
    assert price_for("claude-sonnet-5") is PRICING["claude-sonnet-5"]


def test_unknown_or_missing_model_uses_default():
    assert price_for("some-other-model") is DEFAULT_PRICE
    assert price_for(None) is DEFAULT_PRICE


def test_cost_math_per_million_tokens():
    p = PRICING["claude-opus-5-5"]
    expected = p.input + p.output + p.cache_write + p.cache_read
    assert cost_usd("claude-opus-5-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000) == pytest.approx(expected)
    assert cost_usd("claude-opus-5-5", 0, 0, 0, 0) == 0


def test_pricing_file_overrides_and_extends(tmp_path):
    f = tmp_path / "prices.json"
    f.write_text(json.dumps({"claude-opus-5-5": {"output": 99}, "my-local-model": {"input": 0, "output": 0}}))
    table = load_pricing(f)
    assert table["claude-opus-5-5"].output == 99
    assert table["claude-opus-5-5"].input == PRICING["claude-opus-5-5"].input
    assert cost_usd("my-local-model", 0, 5_000_000, 0, 0, table) == 0
    assert PRICING["claude-opus-5-5"].output != 99  # built-in table untouched


def test_pricing_file_must_be_an_object(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("[1, 2]")
    with pytest.raises(ValueError):
        load_pricing(f)
