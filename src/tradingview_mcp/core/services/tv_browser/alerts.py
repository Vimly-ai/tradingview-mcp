"""Alert management. MVP scope: price-cross alerts only (see §2 of design)."""
from __future__ import annotations

import re
from typing import Any

from . import selectors, symbols


_VALID_DIRECTIONS = {"crossing", "crossing_up", "crossing_down"}
_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?$")


async def create_alert(
    page: Any,
    symbol: str,
    price: float,
    direction: str = "crossing",
    message: str = "",
    expires: str | None = None,
) -> dict:
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"direction {direction!r} not in {sorted(_VALID_DIRECTIONS)}"
        )
    if expires is not None and not _ISO8601_RE.match(expires):
        raise ValueError(
            f"expires {expires!r} must be ISO-8601 (e.g. 2026-12-31T23:59:00Z)"
        )

    canon = symbols.normalize(symbol)
    tv_interval = selectors.TV_INTERVAL_MAP.get("1h", "60")
    chart_url = selectors.CHART_URL_TPL.format(symbol=canon, tv_interval=tv_interval)
    await page.goto(chart_url, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.CHART_READY, timeout=20_000)

    await page.click(selectors.ALERT_CREATE_BTN_TOOLBAR)
    await page.wait_for_selector(selectors.ALERT_DIALOG, timeout=10_000)
    await page.fill(selectors.ALERT_DIALOG_PRICE_INPUT, str(price))
    if message:
        await page.fill(selectors.ALERT_DIALOG_MESSAGE_INPUT, message)
    await page.click(selectors.ALERT_DIALOG_CREATE_BTN)

    warnings: list[str] = []
    if direction != "crossing":
        warnings.append(
            f"direction={direction!r} requested but TV dialog mapping not yet "
            f"wired; alert created with default direction."
        )
    if expires is not None:
        warnings.append(
            f"expires={expires!r} requested but TV dialog mapping not yet "
            f"wired; alert created without expiration."
        )

    return {
        "symbol": canon,
        "price": price,
        "direction": direction,
        "message": message,
        "expires": expires,
        "warnings": warnings,
    }


_DELETE_JS_TPL = """
(alertId) => {
    const row = document.querySelector(`[data-name="alerts-item"][data-alert-id="${alertId}"]`);
    if (!row) return false;
    const btn = row.querySelector('[data-name="alert-delete"]');
    if (!btn) return false;
    btn.click();
    return true;
}
"""


async def delete_alert(page: Any, alert_id: str | int) -> dict:
    await page.goto(selectors.ALERTS_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.ALERT_LIST_ROW, timeout=10_000)
    deleted = await page.evaluate(_DELETE_JS_TPL, str(alert_id))
    return {
        "alert_id": str(alert_id),
        "deleted": bool(deleted),
        "warnings": [],
    }
