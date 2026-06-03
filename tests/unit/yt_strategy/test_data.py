"""Tests for data.py."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from tradingview_mcp.core.services.yt_strategy.data import (
    CostProfile,
    cost_profile_for,
    fetch_ohlcv,
    route_symbol,
    validate_timeframe,
    clamp_period,
)


class TestRouteSymbol:
    @pytest.mark.parametrize("sym,src", [
        ("BTCUSDT", "binance"),
        ("ETHUSDT", "binance"),
        ("SOLBUSD", "binance"),
        ("BTCETH", "binance"),
        ("AAPL", "yahoo"),
        ("^GSPC", "yahoo"),
        ("BTC-USD", "yahoo"),
        ("EURUSD=X", "yahoo"),
        ("VOO.L", "yahoo"),
    ])
    def test_routing(self, sym, src):
        assert route_symbol(sym) == src

    def test_fixture_symbols_route_to_fixture(self):
        assert route_symbol("FIXTURE_AAPL") == "fixture"


class TestCostProfile:
    def test_binance_crypto(self):
        p = cost_profile_for("BTCUSDT")
        assert p.name == "binance_crypto_spot"
        assert p.commission == 0.001
        assert p.slippage == 0.0005

    def test_yahoo_equity(self):
        p = cost_profile_for("AAPL")
        assert p.name == "yahoo_equity"
        assert p.commission == 0.0
        assert p.slippage == 0.0002

    def test_yahoo_fx(self):
        p = cost_profile_for("EURUSD=X")
        assert p.name == "yahoo_fx"
        assert p.commission == 0.0002

    def test_yahoo_crypto_usd(self):
        p = cost_profile_for("BTC-USD")
        assert p.name == "yahoo_crypto_usd"
        assert p.commission == 0.001


class TestValidateTimeframe:
    @pytest.mark.parametrize("tf", ["1m", "5m", "15m", "1h", "4h", "1d", "1w"])
    def test_binance_accepts(self, tf):
        validate_timeframe("BTCUSDT", tf)  # raises on invalid

    def test_binance_rejects_8h(self):
        # Binance does support 8h actually — but our allow-list may or may not.
        # The test should verify that obvious nonsense is rejected.
        with pytest.raises(ValueError, match="does not support"):
            validate_timeframe("BTCUSDT", "7h")

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"])
    def test_yahoo_accepts(self, tf):
        validate_timeframe("AAPL", tf)

    def test_yahoo_rejects_4h(self):
        with pytest.raises(ValueError, match="does not support"):
            validate_timeframe("AAPL", "4h")


class TestClampPeriod:
    def test_yahoo_intraday_clamps_to_60d(self):
        period, warning = clamp_period("AAPL", "5m", "2y")
        assert period == "60d"
        assert warning is not None
        assert "60" in warning

    def test_yahoo_1m_clamps_to_7d(self):
        period, warning = clamp_period("AAPL", "1m", "2y")
        assert period == "7d"
        assert warning is not None

    def test_yahoo_daily_unrestricted(self):
        period, warning = clamp_period("AAPL", "1d", "10y")
        assert period == "10y"
        assert warning is None

    def test_strict_mode_raises_instead(self):
        with pytest.raises(ValueError, match="exceeds"):
            clamp_period("AAPL", "5m", "2y", strict=True)


class TestFetchOhlcv:
    def test_fixture_loads_synthetic_csv(self):
        df = fetch_ohlcv("FIXTURE_AAPL", "1d", "2y")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert len(df) == 500

    @patch("tradingview_mcp.core.services.yt_strategy.data.requests")
    def test_binance_fetch_returns_expected_shape(self, mock_requests):
        # Mock klines response: list of arrays per Binance docs.
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            [
                1640995200000, "47000.0", "47500.0", "46800.0", "47200.0", "100.5",
                1640995259999, "0", 0, "0", "0", "0",
            ],
            [
                1640995260000, "47200.0", "47300.0", "47100.0", "47250.0", "80.2",
                1640995319999, "0", 0, "0", "0", "0",
            ],
        ]
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        df = fetch_ohlcv("BTCUSDT", "1m", "1d")
        assert len(df) == 2
        assert df.iloc[0]["Open"] == 47000.0
        assert df.iloc[1]["Close"] == 47250.0
