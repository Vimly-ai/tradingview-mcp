"""Runtime check that every tv_* MCP tool wraps in debug_on_failure.

Monkeypatch page methods to raise. For each tool's call surface, invoke
through the debug_on_failure context manager directly to confirm the
artifact-writing path is exercised when the tool body fails. If the
wrapper were ever bypassed, the corresponding browser_debug/ folder
would not appear.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser import (
    chart, data, pine, alerts, watchlists, debug as debug_mod,
)


TOOL_CALLS = [
    ("tv_open_chart",            lambda p: chart.open_chart(p, "BTC", "1h")),
    ("tv_screenshot_chart",      lambda p: chart.screenshot_chart(p, "BTC", "1h")),
    ("tv_add_indicator",         lambda p: chart.add_indicator(p, "RSI")),
    ("tv_read_watchlist",        lambda p: data.read_watchlist(p)),
    ("tv_read_alerts",           lambda p: data.read_alerts(p)),
    ("tv_list_my_indicators",    lambda p: data.list_my_indicators(p)),
    ("tv_paste_pine",            lambda p: pine.paste_pine(p, code="x")),
    ("tv_save_indicator",        lambda p: pine.save_indicator(p, "n", "x")),
    ("tv_run_strategy_tester",   lambda p: pine.run_strategy_tester(p, code="x", symbol="BTC", timeframe="1h")),
    ("tv_create_alert",          lambda p: alerts.create_alert(p, "BTC", price=1.0)),
    ("tv_delete_alert",          lambda p: alerts.delete_alert(p, "row-0")),
    ("tv_add_to_watchlist",      lambda p: watchlists.add_to_watchlist(p, "BTC")),
    ("tv_remove_from_watchlist", lambda p: watchlists.remove_from_watchlist(p, "BTC")),
]


def _broken_page():
    page = MagicMock()
    page.goto = AsyncMock(side_effect=RuntimeError("forced"))
    page.wait_for_selector = AsyncMock(side_effect=RuntimeError("forced"))
    page.click = AsyncMock(side_effect=RuntimeError("forced"))
    page.fill = AsyncMock(side_effect=RuntimeError("forced"))
    page.evaluate = AsyncMock(side_effect=RuntimeError("forced"))
    page.screenshot = AsyncMock(return_value=b"\x89PNG")
    page.content = AsyncMock(return_value="<html/>")
    page.url = "https://www.tradingview.com/"
    locator = MagicMock()
    locator.screenshot = AsyncMock(return_value=b"\x89PNG")
    locator.evaluate = AsyncMock(side_effect=RuntimeError("forced"))
    locator.click = AsyncMock(side_effect=RuntimeError("forced"))
    locator.is_visible = AsyncMock(return_value=False)
    locator.text_content = AsyncMock(return_value="")
    page.locator = MagicMock(return_value=locator)
    return page


@pytest.mark.parametrize("tool_name,call", TOOL_CALLS)
async def test_each_tool_wraps_in_debug_on_failure(tool_name, call, tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page = _broken_page()
    with pytest.raises(Exception):
        async with debug_mod.debug_on_failure(page, tool_name):
            await call(page)

    root = tmp_path / "browser_debug"
    matched = [d for d in root.iterdir() if tool_name in d.name] if root.exists() else []
    assert matched, f"No debug folder found for {tool_name} — wrapper may be missing"
