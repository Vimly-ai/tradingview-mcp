"""User-facing symbol -> TV-canonical EXCHANGE:TICKER form.

DISTINCT FROM Phase 1's yt_strategy/data.py::route_symbol(). That decides
which OHLCV upstream (Yahoo vs Binance) to call. This produces the
EXCHANGE:TICKER string TV uses in chart URLs and selectors. The two
functions share no code; keep their routing tables conceptually in sync
when adding new symbol families.
"""
from __future__ import annotations

import re


_BINANCE_QUOTES = ("USDT", "BUSD", "USDC", "TUSD", "FDUSD", "DAI", "BTC", "ETH", "BNB")

_CRYPTO_ALIASES = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "DOT", "AVAX",
    "MATIC", "LINK", "UNI", "ATOM", "LTC", "BCH", "FIL", "NEAR", "APT",
}

# Well-known NASDAQ/NYSE equities that should be prefixed automatically.
# Unknown bare-letter symbols pass through rather than being guessed.
_US_EQUITY_ALIASES = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "NFLX", "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU", "AMAT", "LRCX",
    "KLAC", "MRVL", "SNPS", "CDNS", "ADBE", "CRM", "ORCL", "SAP",
    "PYPL", "SQ", "COIN", "HOOD", "SOFI", "UPST",
    "JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "V", "MA",
    "BRK", "JNJ", "PFE", "MRK", "ABBV", "LLY", "BMY", "GILD", "AMGN",
    "UNH", "CVS", "CI", "HUM",
    "XOM", "CVX", "COP", "SLB", "OXY",
    "DIS", "CMCSA", "T", "VZ", "TMUS",
    "WMT", "TGT", "COST", "AMZN", "HD", "LOW",
    "BA", "LMT", "RTX", "NOC", "GD",
    "GE", "MMM", "CAT", "DE", "HON",
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI",
    "GLD", "SLV", "USO", "UNG",
}


def _looks_like_binance_pair(symbol: str) -> bool:
    if not re.fullmatch(r"[A-Z0-9]+", symbol):
        return False
    return any(symbol.endswith(q) and len(symbol) > len(q) for q in _BINANCE_QUOTES)


def _looks_like_us_equity(symbol: str) -> bool:
    return symbol in _US_EQUITY_ALIASES


def normalize(symbol: str) -> str:
    """Map *symbol* to TV-canonical EXCHANGE:TICKER form.

    Examples:
        normalize("BTC")        -> "BINANCE:BTCUSDT"
        normalize("AAPL")       -> "NASDAQ:AAPL"
        normalize("EURUSD=X")   -> "FX:EURUSD"
        normalize("BTC-USD")    -> "BINANCE:BTCUSDT"
        normalize("BINANCE:X")  -> "BINANCE:X"
    """
    if ":" in symbol:
        return symbol
    if symbol in _CRYPTO_ALIASES:
        return f"BINANCE:{symbol}USDT"
    if symbol.endswith("-USD"):
        base = symbol[:-4]
        return f"BINANCE:{base}USDT"
    if symbol.endswith("=X"):
        return f"FX:{symbol[:-2]}"
    if _looks_like_binance_pair(symbol):
        return f"BINANCE:{symbol}"
    if _looks_like_us_equity(symbol):
        return f"NASDAQ:{symbol}"
    return symbol
