from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingview_mcp.core.services.tv_browser.browser import (
    TVBrowser,
    page_lock,
    reset_singleton,
)
from tradingview_mcp.core.services.tv_browser.exceptions import TVBrowserDead


@pytest.fixture(autouse=True)
def _reset():
    reset_singleton()
    yield
    reset_singleton()


@pytest.fixture
def mock_playwright(monkeypatch):
    mock_page = MagicMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.pages = [mock_page]
    mock_context.close = AsyncMock()
    mock_browser = MagicMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_context.browser = mock_browser

    mock_chromium = MagicMock()
    mock_chromium.launch_persistent_context = AsyncMock(return_value=mock_context)
    mock_pw = MagicMock()
    mock_pw.chromium = mock_chromium
    mock_pw.stop = AsyncMock()

    mock_async_pw = AsyncMock()
    mock_async_pw.start = AsyncMock(return_value=mock_pw)

    monkeypatch.setattr(
        "tradingview_mcp.core.services.tv_browser.browser.async_playwright",
        lambda: mock_async_pw,
    )
    return {"page": mock_page, "context": mock_context, "browser": mock_browser,
            "playwright": mock_pw, "async_pw": mock_async_pw}


async def test_get_page_lazily_launches(mock_playwright, monkeypatch, tmp_path):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    browser = TVBrowser()
    page = await browser.get_page()
    assert page is mock_playwright["page"]
    mock_playwright["playwright"].chromium.launch_persistent_context.assert_called_once()


async def test_page_lock_serializes_callers(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    inside_count = 0
    max_concurrent = 0

    async def use_lock():
        nonlocal inside_count, max_concurrent
        async with page_lock() as page:
            inside_count += 1
            max_concurrent = max(max_concurrent, inside_count)
            await asyncio.sleep(0.05)
            inside_count -= 1

    await asyncio.gather(use_lock(), use_lock(), use_lock())
    assert max_concurrent == 1, "page_lock must serialize callers"


async def test_relaunch_once_on_dead_context(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    browser = TVBrowser()
    await browser.get_page()

    mock_playwright["page"].is_closed.return_value = True

    page = await browser.get_page()
    assert page is mock_playwright["page"]
    assert mock_playwright["playwright"].chromium.launch_persistent_context.call_count == 2


async def test_two_consecutive_failures_raises_dead(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    mock_playwright["playwright"].chromium.launch_persistent_context = AsyncMock(
        side_effect=Exception("chromium failed")
    )
    browser = TVBrowser()
    with pytest.raises(TVBrowserDead):
        await browser.get_page()


async def test_idle_timer_disabled_during_interactive_login(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    monkeypatch.setenv("TV_BROWSER_IDLE_S", "0.05")
    browser = TVBrowser()
    await browser.get_page()
    await browser.disable_idle()
    await asyncio.sleep(0.15)
    assert await browser.is_alive(), "browser should remain alive while idle disabled"
    await browser.enable_idle()
    await browser.shutdown()
