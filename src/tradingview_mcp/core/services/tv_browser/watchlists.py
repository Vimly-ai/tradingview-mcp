"""Watchlist manipulation: add / remove symbols."""
from __future__ import annotations

from typing import Any

from . import selectors, symbols


_REMOVE_JS_TPL = """
(canonSymbol) => {
    const rows = document.querySelectorAll('[data-name="watchlist-symbol-row"]');
    for (const r of rows) {
        if ((r.getAttribute('data-symbol') || '') === canonSymbol) {
            const btn = r.querySelector('[data-name="watchlist-remove"]');
            if (btn) { btn.click(); return true; }
        }
    }
    return false;
}
"""


async def _switch_watchlist(page: Any, name: str) -> None:
    await page.click(selectors.WATCHLIST_DROPDOWN)
    try:
        loc = page.locator(f'div[role="menuitem"]:has-text({name!r})')
        await loc.click(timeout=3000)
    except Exception:
        pass


async def add_to_watchlist(
    page: Any, symbol: str, watchlist_name: str | None = None
) -> dict:
    canon = symbols.normalize(symbol)
    if watchlist_name:
        await _switch_watchlist(page, watchlist_name)

    tv_interval = selectors.TV_INTERVAL_MAP.get("1h", "60")
    url = selectors.CHART_URL_TPL.format(symbol=canon, tv_interval=tv_interval)
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.CHART_READY, timeout=20_000)
    await page.click('button[data-name="add-to-watchlist"]')

    return {
        "symbol": canon,
        "watchlist": watchlist_name or "current",
        "added": True,
        "warnings": [],
    }


async def remove_from_watchlist(
    page: Any, symbol: str, watchlist_name: str | None = None
) -> dict:
    canon = symbols.normalize(symbol)
    if watchlist_name:
        await _switch_watchlist(page, watchlist_name)
    removed = await page.evaluate(_REMOVE_JS_TPL, canon)
    return {
        "symbol": canon,
        "watchlist": watchlist_name or "current",
        "removed": bool(removed),
        "warnings": [],
    }
