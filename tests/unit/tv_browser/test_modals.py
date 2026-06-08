from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.modals import dismiss_modals
from tradingview_mcp.core.services.tv_browser import selectors


async def test_dismiss_modals_clicks_each_known_selector():
    page = MagicMock()
    locator = MagicMock()
    locator.click = AsyncMock()
    locator.wait_for = AsyncMock()
    page.locator = MagicMock(return_value=locator)

    count = await dismiss_modals(page, timeout_s=0.05)

    assert page.locator.call_count == len(selectors.MODAL_DISMISS_SELECTORS)
    assert count == len(selectors.MODAL_DISMISS_SELECTORS)


async def test_dismiss_modals_swallows_per_selector_errors():
    page = MagicMock()
    locator = MagicMock()
    locator.click = AsyncMock(side_effect=Exception("not present"))
    locator.wait_for = AsyncMock(side_effect=Exception("timeout"))
    page.locator = MagicMock(return_value=locator)

    count = await dismiss_modals(page, timeout_s=0.05)
    assert count == 0


async def test_dismiss_modals_idempotent():
    page = MagicMock()
    locator = MagicMock()
    locator.click = AsyncMock(side_effect=Exception("nothing to dismiss"))
    locator.wait_for = AsyncMock(side_effect=Exception("timeout"))
    page.locator = MagicMock(return_value=locator)

    c1 = await dismiss_modals(page, timeout_s=0.05)
    c2 = await dismiss_modals(page, timeout_s=0.05)
    assert c1 == 0 and c2 == 0
