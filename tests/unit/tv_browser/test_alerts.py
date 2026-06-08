from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.alerts import create_alert, delete_alert
from tradingview_mcp.core.services.tv_browser import selectors


def _page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    locator = MagicMock()
    locator.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    return page


async def test_create_alert_clicks_toolbar_and_fills_price():
    page = _page()
    result = await create_alert(page, "BTCUSDT", price=60000, message="BTC up")
    assert any(
        call.args[0] == selectors.ALERT_CREATE_BTN_TOOLBAR
        for call in page.click.call_args_list
    )
    assert any(
        call.args[0] == selectors.ALERT_DIALOG_PRICE_INPUT and call.args[1] == "60000"
        for call in page.fill.call_args_list
    )
    assert any(
        call.args[0] == selectors.ALERT_DIALOG_MESSAGE_INPUT and call.args[1] == "BTC up"
        for call in page.fill.call_args_list
    )
    assert result["symbol"]
    assert result["price"] == 60000


async def test_create_alert_rejects_unknown_direction():
    page = _page()
    with pytest.raises(ValueError, match="direction"):
        await create_alert(page, "BTCUSDT", price=60000, direction="weird")


async def test_create_alert_rejects_invalid_expires():
    page = _page()
    with pytest.raises(ValueError, match="expires"):
        await create_alert(page, "BTCUSDT", price=60000, expires="next-tuesday")


async def test_create_alert_accepts_iso8601_expires():
    page = _page()
    result = await create_alert(page, "BTCUSDT", price=60000, expires="2026-12-31T23:59:00Z")
    assert result["expires"] == "2026-12-31T23:59:00Z"


async def test_delete_alert_navigates_and_clicks():
    page = _page()
    page.evaluate = AsyncMock(return_value=True)
    result = await delete_alert(page, "row-0")
    page.goto.assert_called_once()
    assert "/alerts" in page.goto.call_args.args[0]
    assert result["alert_id"] == "row-0"
    assert result["deleted"] is True
