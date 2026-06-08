"""Login detection, interactive login, logout (via user_data_dir rmtree)."""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any

from .browser import _get_singleton, _user_data_dir
from .exceptions import TVSessionExpired, TVLoginTimeout
from .selectors import LOGGED_IN_INDICATOR, LOGIN_URL, _TV_BASE


_USER_MENU_SELECTOR_CANDIDATES = (
    LOGGED_IN_INDICATOR,
    'button[aria-label*="user menu" i]',
    'button[aria-label*="account" i]',
    '[data-name="header-user-menu-button"]',
    'button.tv-header__user-menu-button',
    '[class*="userMenuButton"]',
)


async def is_logged_in(page: Any, timeout_s: float = 2.0) -> bool:
    """True if the current page shows a logged-in TradingView session.

    Strategy (most reliable first):
    1. Check for a non-empty ``sessionid`` cookie on a ``.tradingview.com``
       domain. This is the canonical "logged in" signal and survives DOM
       redesigns.
    2. If that's absent, fall back to any of several known user-menu DOM
       selectors (TV ships subtle variations across redesigns).

    Navigates to tradingview.com first if the page is currently elsewhere
    (so cookie lookup and selector matching work against the right context).
    """
    try:
        if "tradingview.com" not in (page.url or "") and "127.0.0.1" not in (page.url or ""):
            await page.goto(_TV_BASE, wait_until="domcontentloaded")

        # Method 1: cookie-based (most reliable)
        try:
            cookies = await page.context.cookies()
        except Exception:
            cookies = []
        for c in cookies:
            if not isinstance(c, dict):
                continue
            if c.get("name") != "sessionid":
                continue
            domain = (c.get("domain") or "").lower()
            if "tradingview.com" in domain and c.get("value"):
                return True

        # Method 2: try multiple known user-menu selectors
        per_selector_timeout = max(200, int(timeout_s * 1000 / max(1, len(_USER_MENU_SELECTOR_CANDIDATES))))
        for sel in _USER_MENU_SELECTOR_CANDIDATES:
            try:
                await page.locator(sel).first.wait_for(
                    state="visible", timeout=per_selector_timeout
                )
                return True
            except Exception:
                continue

        return False
    except Exception:
        return False


async def require_login(page: Any) -> None:
    """Raise TVSessionExpired if not currently logged in."""
    if not await is_logged_in(page):
        raise TVSessionExpired("TradingView session not active.")


async def interactive_login(
    page: Any, timeout_s: float = 300.0, poll_s: float = 2.0
) -> None:
    """Open the login page and poll until is_logged_in or timeout."""
    inst = _get_singleton()
    await inst.disable_idle()
    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if await is_logged_in(page, timeout_s=1.0):
                return
            await asyncio.sleep(poll_s)
        raise TVLoginTimeout(
            f"Login not completed within {timeout_s:.0f}s."
        )
    finally:
        await inst.enable_idle()


async def logout() -> None:
    """Close the browser and delete the persistent user_data_dir."""
    inst = _get_singleton()
    try:
        await inst.shutdown()
    except Exception:
        pass
    udd = Path(_user_data_dir())
    if udd.exists():
        shutil.rmtree(udd, ignore_errors=True)
