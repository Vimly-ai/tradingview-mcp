from __future__ import annotations

from tradingview_mcp.core.services.yt_strategy.rule_extractor import (
    StrategySpec,
    extract_rules,
)


def test_strategy_spec_default_fields():
    s = StrategySpec()
    assert s.name == ""
    assert s.entry_rules == []
    assert s.exit_rules == []
    assert s.indicators_used == []
    assert s.timeframe_hint is None
    assert s.asset_hint is None
    assert s.position_sizing is None
    assert s.risk_management is None
    assert s.confidence == 0.0


def test_extract_rules_stub_wraps_transcript():
    spec = extract_rules("Buy when RSI is below 30, sell when above 70.")
    assert isinstance(spec, StrategySpec)
    assert spec.entry_rules == ["Buy when RSI is below 30, sell when above 70."]
    assert spec.confidence < 0.5
    assert spec.raw_transcript == "Buy when RSI is below 30, sell when above 70."


def test_extract_rules_empty_transcript():
    spec = extract_rules("")
    assert spec.entry_rules == []
    assert spec.confidence == 0.0
