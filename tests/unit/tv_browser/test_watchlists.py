from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.watchlists import (
    add_to_watchlist, remove_from_watchlist,
)


def _page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    locator = MagicMock()
    locator.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    return page


async def test_add_to_watchlist_returns_normalized_symbol():
    page = _page()
    result = await add_to_watchlist(page, "BTC")
    assert result["symbol"] == "BINANCE:BTCUSDT"
    assert result["added"] is True


async def test_remove_from_watchlist_runs_evaluate():
    page = _page()
    result = await remove_from_watchlist(page, "BTCUSDT")
    page.evaluate.assert_called_once()
    assert result["symbol"] == "BINANCE:BTCUSDT"
    assert result["removed"] is True


async def test_add_to_watchlist_selects_named_list():
    page = _page()
    await add_to_watchlist(page, "BTC", watchlist_name="crypto-shortlist")
    assert page.click.call_count >= 1
