from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_mcp.core.services.yt_strategy.runner import run_backtest


def _benign_code():
    return (Path(__file__).resolve().parents[2] / "fixtures" / "strategies" / "sma_cross.py").read_text()


def test_run_backtest_with_fixture_symbol(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    result = run_backtest(
        strategy_code=_benign_code(),
        symbol="FIXTURE_AAPL",
        timeframe="1d",
        period="2y",
        slug="test-iter1",
        oos_validate=True,
    )
    assert "in_sample" in result
    assert "out_of_sample" in result
    assert "benchmark" in result
    assert "overfit_flag" in result
    assert "run_path" in result
    assert "cost_profile" in result
    # File system: artifacts persisted
    run_dir = tmp_path / "strategies" / "test-iter1"
    assert (run_dir / "strategy.py").exists()
    assert (run_dir / "report.json").exists()

def test_run_backtest_buy_and_hold_benchmark_present(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    result = run_backtest(
        strategy_code=_benign_code(),
        symbol="FIXTURE_AAPL",
        timeframe="1d",
        period="2y",
        slug="bh-test",
    )
    assert "bh_return_pct" in result["benchmark"]
