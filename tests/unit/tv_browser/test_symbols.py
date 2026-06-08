from __future__ import annotations

import pytest

from tradingview_mcp.core.services.tv_browser.symbols import normalize


class TestNormalize:
    @pytest.mark.parametrize("user,canonical", [
        # Crypto aliases
        ("BTC", "BINANCE:BTCUSDT"),
        ("ETH", "BINANCE:ETHUSDT"),
        ("SOL", "BINANCE:SOLUSDT"),
        # Bare alphanumeric ending in known quote
        ("BTCUSDT", "BINANCE:BTCUSDT"),
        ("ETHBTC", "BINANCE:ETHBTC"),
        ("SOLBUSD", "BINANCE:SOLBUSD"),
        # US equity tickers
        ("AAPL", "NASDAQ:AAPL"),
        ("TSLA", "NASDAQ:TSLA"),
        # FX (Yahoo-style)
        ("EURUSD=X", "FX:EURUSD"),
        ("GBPUSD=X", "FX:GBPUSD"),
        # Already-prefixed pass through
        ("BINANCE:DOGEUSDT", "BINANCE:DOGEUSDT"),
        ("NYSE:GE", "NYSE:GE"),
        ("FX:USDJPY", "FX:USDJPY"),
    ])
    def test_routing(self, user, canonical):
        assert normalize(user) == canonical

    def test_yahoo_crypto_usd_converts(self):
        assert normalize("BTC-USD") == "BINANCE:BTCUSDT"
        assert normalize("ETH-USD") == "BINANCE:ETHUSDT"

    def test_unknown_passes_through(self):
        assert normalize("WEIRD") == "WEIRD"
        assert normalize("VOO.L") == "VOO.L"

    def test_index_symbols_pass_through_or_known(self):
        assert normalize("^GSPC") == "^GSPC"
