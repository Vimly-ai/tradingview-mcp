"""Chart canvas operations: open chart, screenshot, add indicator."""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

from . import selectors, symbols
from .debug import rotate_artifacts


def _screenshot_dir() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    d = Path(base) / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_screenshot(png: bytes, label: str) -> Path:
    ts = time.strftime("%Y-%m-%dT%H-%M-%S")
    safe_label = "".join(c if c.isalnum() or c in "-._" else "_" for c in label)
    path = _screenshot_dir() / f"{ts}-{safe_label}.png"
    path.write_bytes(png)
    rotate_artifacts(_screenshot_dir(), max_count=100)
    return path


async def open_chart(
    page: Any, symbol: str, timeframe: str, indicators: list[str] | None = None
) -> dict:
    canon = symbols.normalize(symbol)
    tv_interval = selectors.TV_INTERVAL_MAP.get(timeframe, timeframe)
    url = selectors.CHART_URL_TPL.format(symbol=canon, tv_interval=tv_interval)
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.CHART_READY, timeout=20_000)

    if indicators:
        for ind in indicators:
            await add_indicator(page, ind)

    return {
        "symbol": canon,
        "timeframe": timeframe,
        "url": url,
        "warnings": [],
    }


async def screenshot_chart(
    page: Any,
    symbol: str | None = None,
    timeframe: str | None = None,
    region: str = "main",
) -> dict:
    if symbol is not None:
        await open_chart(page, symbol, timeframe or "1h")
        canon = symbols.normalize(symbol)
        tf = timeframe or "1h"
    else:
        canon = "current"
        tf = "current"

    region_selector = {
        "main": selectors.MAIN_CHART_CANVAS,
        "full": "body",
        "footer": selectors.STRATEGY_TESTER_REPORT_REGION,
    }.get(region, selectors.MAIN_CHART_CANVAS)

    png = await page.locator(region_selector).screenshot()
    path = _save_screenshot(png, f"{canon}-{tf}")

    return {
        "type": "image",
        "data": base64.b64encode(png).decode("ascii"),
        "mimeType": "image/png",
        "path": str(path),
        "symbol": canon,
        "timeframe": tf,
        "region": region,
        "warnings": [],
    }


async def add_indicator(page: Any, name: str) -> dict:
    """Open the indicator dialog, search by name, click first result."""
    await page.fill(selectors.INDICATOR_SEARCH_DIALOG_INPUT, name)
    await page.click(selectors.INDICATOR_DIALOG_FIRST_RESULT)
    return {"indicator": name, "warnings": []}
