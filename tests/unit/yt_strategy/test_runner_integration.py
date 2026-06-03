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


def test_run_backtest_no_overfit_when_all_oos_folds_fail(tmp_path, monkeypatch):
    """When OOS folds all fail, overfit_flag must NOT be True and a warning must be present."""
    import tradingview_mcp.core.services.yt_strategy.runner as runner_mod
    from tradingview_mcp.core.services.yt_strategy.runner import StrategyRuntimeError

    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))

    # Make every OOS fold raise by patching exec_strategy_in_subprocess to fail on small inputs.
    orig = runner_mod.exec_strategy_in_subprocess
    def selective_exec(code, bars, **kw):
        # First call (IS, full window) succeeds; later calls (OOS folds) fail.
        if len(bars) < 200:
            raise StrategyRuntimeError("forced", user_code_line=None, user_code_snippet=None)
        return orig(code, bars, **kw)

    monkeypatch.setattr(runner_mod, "exec_strategy_in_subprocess", selective_exec)
    result = runner_mod.run_backtest(
        strategy_code=_benign_code(),
        symbol="FIXTURE_AAPL",
        timeframe="1d",
        period="2y",
        slug="oos-fail-test",
        oos_validate=True,
    )
    assert result["overfit_flag"] is False
    assert any("walk-forward folds failed" in w for w in result["warnings"])


def test_run_backtest_surfaces_clamp_warning(tmp_path, monkeypatch):
    """When fetch_ohlcv clamps a too-long period, the warning must reach report['warnings']."""
    import tradingview_mcp.core.services.yt_strategy.runner as runner_mod
    import pandas as pd
    from pathlib import Path

    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))

    # Fake fetch_ohlcv to return a DataFrame with a clamp warning attached.
    csv = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_ohlcv.csv"
    df = pd.read_csv(csv, parse_dates=["Date"], index_col="Date")
    df.attrs["clamp_warning"] = "Period '2y' exceeds Yahoo '5m' cap; clamped to '60d'."

    monkeypatch.setattr(runner_mod, "fetch_ohlcv", lambda *a, **kw: df)
    result = runner_mod.run_backtest(
        strategy_code=_benign_code(),
        symbol="AAPL",
        timeframe="5m",
        period="2y",
        slug="clamp-test",
    )
    assert any("clamped" in w.lower() for w in result["warnings"])
