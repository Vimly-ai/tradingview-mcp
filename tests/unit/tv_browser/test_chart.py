from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.chart import (
    open_chart, screenshot_chart, add_indicator,
)
from tradingview_mcp.core.services.tv_browser import selectors


def _page():
    page = MagicMock()
    page.url = ""
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    locator = MagicMock()
    locator.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfake")
    locator.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    return page, locator


async def test_open_chart_navigates_to_normalized_url(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page, _ = _page()
    result = await open_chart(page, "BTC", "1h")
    page.goto.assert_called_once()
    url = page.goto.call_args.args[0]
    assert "BINANCE:BTCUSDT" in url
    assert "interval=60" in url
    assert result["symbol"] == "BINANCE:BTCUSDT"
    assert result["timeframe"] == "1h"


async def test_screenshot_chart_returns_mcp_image_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page, locator = _page()
    result = await screenshot_chart(page, symbol="BTCUSDT", timeframe="1h")
    assert result["type"] == "image"
    assert result["mimeType"] == "image/png"
    assert base64.b64decode(result["data"]).startswith(b"\x89PNG")
    assert result["path"].endswith(".png")
    assert "warnings" in result


async def test_screenshot_chart_no_symbol_uses_current(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page, locator = _page()
    page.url = "https://www.tradingview.com/chart/?symbol=BINANCE:ETHUSDT&interval=60"
    result = await screenshot_chart(page, symbol=None)
    page.goto.assert_not_called()
    assert result["type"] == "image"


async def test_add_indicator_opens_dialog(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page, locator = _page()
    await add_indicator(page, "RSI")
    # The open button must be clicked BEFORE fill
    assert any(
        call.args[0] == selectors.INDICATOR_DIALOG_OPEN_BTN
        for call in page.click.call_args_list
    ), "add_indicator must click the dialog-open button before filling search"
    page.fill.assert_called_once()
    fill_args = page.fill.call_args.args
    assert fill_args[0] == selectors.INDICATOR_SEARCH_DIALOG_INPUT
    assert fill_args[1] == "RSI"
