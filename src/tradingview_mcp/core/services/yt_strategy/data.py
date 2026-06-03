"""Unified OHLCV fetch (Yahoo + Binance) + cost profiles."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests


@dataclass(frozen=True)
class CostProfile:
    name: str
    commission: float   # fraction, e.g. 0.001 = 10 bps
    slippage: float


_BINANCE_QUOTES = ("USDT", "BUSD", "USDC", "TUSD", "FDUSD", "DAI", "BTC", "ETH", "BNB")
_BINANCE_TIMEFRAMES = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M")
_YAHOO_TIMEFRAMES = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo")

# Yahoo intraday period caps (per Yahoo's own restrictions).
_YAHOO_INTRADAY_MAX_PERIOD = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "90m": "60d",
    "1h": "730d",
}


def route_symbol(symbol: str) -> str:
    """Decide which data source to use for *symbol*.

    Returns: "fixture" | "binance" | "yahoo"
    """
    if symbol.startswith("FIXTURE_"):
        return "fixture"
    # Binance pair convention: bare alphanumeric ending with a known quote asset
    if re.fullmatch(r"[A-Z0-9]+", symbol):
        for q in _BINANCE_QUOTES:
            if symbol.endswith(q) and len(symbol) > len(q):
                return "binance"
    return "yahoo"


def cost_profile_for(symbol: str) -> CostProfile:
    """Return realistic commission/slippage defaults for *symbol*."""
    src = route_symbol(symbol)
    if src == "binance":
        return CostProfile("binance_crypto_spot", 0.001, 0.0005)
    if symbol.endswith("=X"):
        return CostProfile("yahoo_fx", 0.0002, 0.0001)
    if symbol.endswith("-USD"):
        return CostProfile("yahoo_crypto_usd", 0.001, 0.0005)
    return CostProfile("yahoo_equity", 0.0, 0.0002)


def validate_timeframe(symbol: str, timeframe: str) -> None:
    """Raise ValueError if *timeframe* isn't supported by the routed source."""
    src = route_symbol(symbol)
    if src == "binance" and timeframe not in _BINANCE_TIMEFRAMES:
        raise ValueError(
            f"Binance does not support timeframe {timeframe!r}; "
            f"valid: {', '.join(_BINANCE_TIMEFRAMES)}"
        )
    if src == "yahoo" and timeframe not in _YAHOO_TIMEFRAMES:
        raise ValueError(
            f"Yahoo does not support timeframe {timeframe!r}; "
            f"valid: {', '.join(_YAHOO_TIMEFRAMES)}"
        )


def _period_to_days(period: str) -> int:
    """Approximate period string → days. Used only for clamp comparisons."""
    if period.endswith("d"):
        return int(period[:-1])
    if period.endswith("mo"):
        return int(period[:-2]) * 30
    if period.endswith("y"):
        return int(period[:-1]) * 365
    if period.endswith("wk"):
        return int(period[:-2]) * 7
    if period.endswith("w"):
        return int(period[:-1]) * 7
    return 999_999  # unknown — treat as "very long"; clamp will trigger


def clamp_period(
    symbol: str, timeframe: str, period: str, strict: bool = False
) -> tuple[str, str | None]:
    """If *period* exceeds the source's cap for *timeframe*, clamp it.

    Returns ``(effective_period, warning_or_None)``. With ``strict=True``,
    raises ``ValueError`` instead of clamping.
    """
    src = route_symbol(symbol)
    if src != "yahoo":
        return period, None
    cap = _YAHOO_INTRADAY_MAX_PERIOD.get(timeframe)
    if cap is None:
        return period, None  # daily/weekly/monthly — long histories ok
    if _period_to_days(period) <= _period_to_days(cap):
        return period, None
    if strict:
        raise ValueError(
            f"Yahoo {timeframe} period {period!r} exceeds max {cap!r}"
        )
    return cap, (
        f"Period {period!r} exceeds Yahoo {timeframe!r} cap; clamped to {cap!r}."
    )


def _binance_base() -> str:
    return os.environ.get("BINANCE_API_BASE", "https://api.binance.com").rstrip("/")


def _fetch_binance(symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
    url = f"{_binance_base()}/api/v3/klines"
    resp = requests.get(
        url,
        params={"symbol": symbol, "interval": timeframe, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "Open", "High", "Low", "Close", "Volume",
            "close_time", "qav", "trades", "tbbv", "tbqv", "ignore",
        ],
    )
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = df[col].astype(float)
    df["Date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
    return df


def _fetch_yahoo(symbol: str, timeframe: str, period: str) -> pd.DataFrame:
    """Direct fetch via Yahoo's chart API."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    resp = requests.get(
        url,
        params={"interval": timeframe, "range": period, "includePrePost": "false"},
        headers={"User-Agent": "Mozilla/5.0 (compatible; tradingview-mcp/0.7)"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    result = body.get("chart", {}).get("result", [])
    if not result:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    r = result[0]
    ts = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    df = pd.DataFrame({
        "Open": quote.get("open", []),
        "High": quote.get("high", []),
        "Low":  quote.get("low", []),
        "Close": quote.get("close", []),
        "Volume": quote.get("volume", []),
    }, index=pd.to_datetime(ts, unit="s", utc=True))
    df.index.name = "Date"
    return df.dropna(subset=["Close"])


def _fetch_fixture(symbol: str) -> pd.DataFrame:
    """Load the synthetic CSV used by integration tests."""
    # File lives at <repo_root>/tests/fixtures/synthetic_ohlcv.csv
    # __file__ is at .../src/tradingview_mcp/core/services/yt_strategy/data.py
    repo_root = Path(__file__).resolve().parents[5]
    csv = repo_root / "tests" / "fixtures" / "synthetic_ohlcv.csv"
    df = pd.read_csv(csv, parse_dates=["Date"], index_col="Date")
    return df


def fetch_ohlcv(symbol: str, timeframe: str, period: str, *, strict_period: bool = False) -> pd.DataFrame:
    """Fetch OHLCV bars for *symbol* with normalized DataFrame shape.

    Returns a UTC-indexed DataFrame with columns Open, High, Low, Close, Volume.
    Raises ValueError on invalid timeframe.
    """
    src = route_symbol(symbol)
    if src == "fixture":
        return _fetch_fixture(symbol)
    validate_timeframe(symbol, timeframe)
    effective_period, _warning = clamp_period(symbol, timeframe, period, strict=strict_period)

    if src == "binance":
        return _fetch_binance(symbol, timeframe)
    return _fetch_yahoo(symbol, timeframe, effective_period)
