from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_mcp.core.services.yt_strategy.autotune import auto_tune


def _rsi_code():
    return (Path(__file__).resolve().parents[2] / "fixtures" / "strategies" / "rsi_oscillator.py").read_text()


def test_auto_tune_returns_expected_shape():
    result = auto_tune(
        strategy_code=_rsi_code(),
        param_grid={"rsi_period": [10, 14, 21], "oversold": [25, 30, 35]},
        symbol="FIXTURE_AAPL",
        timeframe="1d",
        period="2y",
        method="grid",
        max_tries=9,
    )
    assert "best_params" in result
    assert "best_metric" in result
    assert "metric_name" in result
    assert "all_trials" in result
    assert result["metric_name"] == "Sharpe Ratio"

def test_auto_tune_is_deterministic_with_seed():
    r1 = auto_tune(
        strategy_code=_rsi_code(),
        param_grid={"rsi_period": [10, 14, 21], "oversold": [25, 30, 35]},
        symbol="FIXTURE_AAPL", timeframe="1d", period="2y",
        method="grid", max_tries=9, seed=42,
    )
    r2 = auto_tune(
        strategy_code=_rsi_code(),
        param_grid={"rsi_period": [10, 14, 21], "oversold": [25, 30, 35]},
        symbol="FIXTURE_AAPL", timeframe="1d", period="2y",
        method="grid", max_tries=9, seed=42,
    )
    assert r1["best_params"] == r2["best_params"]
    assert r1["best_metric"] == r2["best_metric"]


def test_auto_tune_handler_translates_timeout(monkeypatch):
    """auto_tune_strategy MCP handler should convert TimeoutError to a strategy error envelope, not propagate it."""
    import tradingview_mcp.server as srv
    from tradingview_mcp.core.errors import is_error

    def _fake_auto_tune(*args, **kwargs):
        raise TimeoutError("auto_tune exceeded budget.")

    monkeypatch.setattr(srv, "auto_tune", _fake_auto_tune)
    result = srv.auto_tune_strategy(
        strategy_code="from backtesting import Strategy\nclass S(Strategy):\n    def init(self): pass\n    def next(self): pass\n",
        param_grid={"x": [1]}, symbol="FIXTURE_AAPL", timeframe="1d", period="2y",
    )
    assert is_error(result)
    assert result["error"]["code"] == "STRATEGY_TIMEOUT"


def test_auto_tune_handler_translates_runtime(monkeypatch):
    """auto_tune_strategy MCP handler should convert RuntimeError to a strategy error envelope."""
    import tradingview_mcp.server as srv
    from tradingview_mcp.core.errors import is_error

    def _fake_auto_tune(*args, **kwargs):
        raise RuntimeError("auto_tune subprocess produced no result.")

    monkeypatch.setattr(srv, "auto_tune", _fake_auto_tune)
    result = srv.auto_tune_strategy(
        strategy_code="from backtesting import Strategy\nclass S(Strategy):\n    def init(self): pass\n    def next(self): pass\n",
        param_grid={"x": [1]}, symbol="FIXTURE_AAPL", timeframe="1d", period="2y",
    )
    assert is_error(result)
    assert result["error"]["code"] == "STRATEGY_RUNTIME_ERROR"
