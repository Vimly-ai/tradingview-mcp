from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.data import (
    read_watchlist, read_alerts, list_my_indicators,
)
from tradingview_mcp.core.services.tv_browser.exceptions import TVDOMShapeChanged


def _page_with_evaluate(return_value):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock(return_value=return_value)
    page.url = "https://www.tradingview.com/"
    return page


async def test_read_watchlist_returns_rows():
    rows = [
        {"symbol": "BTCUSDT", "price": "50000", "change_pct": "1.2", "change_abs": "600"},
        {"symbol": "ETHUSDT", "price": "3000", "change_pct": "-0.5", "change_abs": "-15"},
    ]
    page = _page_with_evaluate(rows)
    result = await read_watchlist(page)
    assert result["name"]
    assert len(result["rows"]) == 2
    assert result["rows"][0]["symbol"] == "BTCUSDT"


async def test_read_watchlist_empty():
    page = _page_with_evaluate([])
    result = await read_watchlist(page)
    assert result["rows"] == []


async def test_read_alerts_returns_alerts():
    items = [
        {"symbol": "BTCUSDT", "condition": "crossing 60000",
         "message": "BTC up", "active": True, "alert_id": "row-0"},
    ]
    page = _page_with_evaluate(items)
    result = await read_alerts(page)
    page.goto.assert_called_once()
    assert "/alerts" in page.goto.call_args.args[0]
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["alert_id"] == "row-0"


async def test_list_my_indicators():
    items = [
        {"name": "yt_strategy_BTCUSDT-1h-iter2",
         "last_modified": "2026-06-04T12:00:00Z",
         "tv_script_id": "PUB;abc123"},
    ]
    page = _page_with_evaluate(items)
    result = await list_my_indicators(page)
    page.goto.assert_called_once()
    assert "/scripts/yours" in page.goto.call_args.args[0]
    assert result["indicators"][0]["name"].startswith("yt_strategy_")


async def test_read_watchlist_raises_dom_shape_changed_on_invalid():
    page = _page_with_evaluate("not a list")
    with pytest.raises(TVDOMShapeChanged):
        await read_watchlist(page)
