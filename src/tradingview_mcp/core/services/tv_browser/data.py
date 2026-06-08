"""Read-only DOM scraping: watchlist, alerts, indicators."""
from __future__ import annotations

from typing import Any

from . import selectors
from .exceptions import TVDOMShapeChanged


_WATCHLIST_EXTRACT_JS = """
() => {
    const rows = Array.from(document.querySelectorAll('[data-name="watchlist-symbol-row"]'));
    return rows.map(r => ({
        symbol: r.getAttribute('data-symbol') || (r.querySelector('[data-name="symbol"]') || {}).textContent || '',
        price: (r.querySelector('[data-name="last-price"]') || {}).textContent || '',
        change_pct: (r.querySelector('[data-name="change-pct"]') || {}).textContent || '',
        change_abs: (r.querySelector('[data-name="change-abs"]') || {}).textContent || '',
    }));
}
"""

_ALERTS_EXTRACT_JS = """
() => {
    const items = Array.from(document.querySelectorAll('[data-name="alerts-item"]'));
    return items.map((it, i) => ({
        symbol: (it.querySelector('[data-name="symbol"]') || {}).textContent || '',
        condition: (it.querySelector('[data-name="condition"]') || {}).textContent || '',
        message: (it.querySelector('[data-name="message"]') || {}).textContent || '',
        active: !it.classList.contains('inactive'),
        alert_id: it.getAttribute('data-alert-id') || `row-${i}`,
    }));
}
"""

_INDICATORS_EXTRACT_JS = """
() => {
    const items = Array.from(document.querySelectorAll('[data-name="indicator-list-item"]'));
    return items.map(it => ({
        name: (it.querySelector('[data-name="indicator-name"]') || {}).textContent || '',
        last_modified: it.getAttribute('data-last-modified') || '',
        tv_script_id: it.getAttribute('data-script-id') || '',
    }));
}
"""


async def read_watchlist(page: Any, name: str | None = None) -> dict:
    warnings: list[str] = []
    if name is not None:
        warnings.append(
            f"name={name!r} requested but watchlist-switching DOM selector "
            f"not yet wired; returning currently-visible watchlist."
        )
    rows = await page.evaluate(_WATCHLIST_EXTRACT_JS)
    if not isinstance(rows, list):
        raise TVDOMShapeChanged("watchlist rows extraction returned non-list", panel="watchlist")
    return {
        "name": name or "current",
        "rows": rows,
        "warnings": warnings,
    }


async def read_alerts(page: Any) -> dict:
    await page.goto(selectors.ALERTS_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.ALERT_LIST_ROW, timeout=10_000)
    alerts = await page.evaluate(_ALERTS_EXTRACT_JS)
    if not isinstance(alerts, list):
        raise TVDOMShapeChanged("alerts extraction returned non-list", panel="alerts")
    return {
        "alerts": alerts,
        "warnings": [],
    }


async def list_my_indicators(page: Any) -> dict:
    await page.goto(selectors.PINE_LIBRARY_URL, wait_until="domcontentloaded")
    items = await page.evaluate(_INDICATORS_EXTRACT_JS)
    if not isinstance(items, list):
        raise TVDOMShapeChanged("indicator list returned non-list", panel="pine_library")
    return {
        "indicators": items,
        "warnings": [],
    }
