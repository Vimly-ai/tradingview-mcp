from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.session import (
    is_logged_in,
    require_login,
    interactive_login,
    logout,
)
from tradingview_mcp.core.services.tv_browser.exceptions import (
    TVSessionExpired,
    TVLoginTimeout,
)


def _mock_page(url: str = "https://www.tradingview.com/chart/", cookies=None):
    """Build a page mock. By default no cookies → forces selector fallback."""
    page = MagicMock()
    page.url = url
    page.goto = AsyncMock()
    # context.cookies() returns whatever the test wants; default empty list
    page.context = MagicMock()
    page.context.cookies = AsyncMock(return_value=cookies or [])
    locator = MagicMock()
    locator.wait_for = AsyncMock()
    # .first chains: page.locator(sel).first.wait_for(...)
    locator.first = locator
    page.locator = MagicMock(return_value=locator)
    return page, locator


async def test_is_logged_in_true_when_indicator_visible():
    # No cookies → selector path matches → True
    page, locator = _mock_page()
    locator.wait_for = AsyncMock()  # resolves -> visible
    assert await is_logged_in(page) is True


async def test_is_logged_in_true_when_session_cookie_present():
    cookies = [{"name": "sessionid", "value": "abc123",
                "domain": ".tradingview.com", "path": "/"}]
    page, locator = _mock_page(cookies=cookies)
    # Selector lookup should NEVER be needed when cookies signal logged-in.
    locator.wait_for = AsyncMock(side_effect=Exception("should not be reached"))
    assert await is_logged_in(page) is True


async def test_is_logged_in_false_when_indicator_absent():
    page, locator = _mock_page()
    locator.wait_for = AsyncMock(side_effect=Exception("not visible"))
    assert await is_logged_in(page) is False


async def test_is_logged_in_navigates_when_not_on_tv():
    page, locator = _mock_page(url="about:blank")
    locator.wait_for = AsyncMock()
    await is_logged_in(page)
    page.goto.assert_called_once()
    assert "tradingview.com" in page.goto.call_args.args[0]


async def test_require_login_raises_when_not_logged_in():
    page, locator = _mock_page()
    locator.wait_for = AsyncMock(side_effect=Exception("nope"))
    with pytest.raises(TVSessionExpired):
        await require_login(page)


async def test_interactive_login_times_out():
    page, locator = _mock_page()
    locator.wait_for = AsyncMock(side_effect=Exception("never logs in"))
    with pytest.raises(TVLoginTimeout):
        await interactive_login(page, timeout_s=0.5, poll_s=0.1)


async def test_interactive_login_succeeds_when_cookie_appears():
    page, locator = _mock_page()
    # No cookies on first 2 polls, sessionid cookie on 3rd
    page.context.cookies = AsyncMock(side_effect=[
        [],
        [],
        [{"name": "sessionid", "value": "x", "domain": ".tradingview.com"}],
    ])
    # Selectors always fail to avoid masking the cookie test
    locator.wait_for = AsyncMock(side_effect=Exception("selector miss"))
    await interactive_login(page, timeout_s=2.0, poll_s=0.05)


async def test_logout_removes_user_data_dir(tmp_path, monkeypatch):
    udd = tmp_path / "browser"
    udd.mkdir()
    (udd / "Cookies").write_text("fake cookie data")
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(udd))

    from tradingview_mcp.core.services.tv_browser.browser import reset_singleton
    reset_singleton()

    await logout()
    assert not udd.exists(), "logout should delete the user_data_dir"
