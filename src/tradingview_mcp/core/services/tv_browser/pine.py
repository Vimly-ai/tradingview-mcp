"""Pine Editor + Strategy Tester — the Phase 1 → Phase 2 closure point."""
from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from . import selectors, symbols
from .exceptions import TVPineCompileError


def _strategy_path(slug: str) -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    return Path(base) / "strategies" / slug / "strategy.pine"


async def _set_monaco_value(page: Any, code: str) -> None:
    """Replace the Pine Editor's Monaco content with *code*."""
    js = f"""
    () => {{
        const code = {json.dumps(code)};
        if (window.monaco && monaco.editor && monaco.editor.getEditors().length) {{
            const editor = monaco.editor.getEditors()[0];
            editor.setValue(code);
            return true;
        }}
        return false;
    }}
    """
    await page.evaluate(js)


async def _pine_compile_error(page: Any) -> tuple[str, int | None] | None:
    """Read TV's Pine error panel. Returns (full_text, first_line) or None."""
    try:
        loc = page.locator(selectors.PINE_EDITOR_ERROR_PANEL)
        if not await loc.is_visible():
            return None
        text = (await loc.text_content()) or ""
        if not text.strip():
            return None
        m = re.search(r"line\s+(\d+)", text)
        line = int(m.group(1)) if m else None
        return text, line
    except Exception:
        return None


async def paste_pine(
    page: Any,
    code: str | None = None,
    slug: str | None = None,
    name: str | None = None,
    save: bool = True,
    add_to_chart: bool = False,
) -> dict:
    if (code is None) == (slug is None):
        raise ValueError("paste_pine requires exactly one of code or slug.")

    if slug is not None:
        path = _strategy_path(slug)
        if not path.exists():
            raise FileNotFoundError(f"No Pine source at {path}")
        code = path.read_text()

    if "/pine-editor/" not in (page.url or ""):
        await page.goto(selectors.PINE_EDITOR_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.PINE_EDITOR_READY, timeout=20_000)

    await _set_monaco_value(page, code or "")

    err = await _pine_compile_error(page)
    if err:
        text, line = err
        raise TVPineCompileError(
            f"Pine compile error: {text.splitlines()[0]}",
            full_text=text,
            line=line,
        )

    saved = False
    if save:
        await page.click(selectors.PINE_EDITOR_SAVE_BTN)
        if name:
            await page.fill(selectors.SAVE_DIALOG_NAME_INPUT, name)
        await page.click(selectors.SAVE_DIALOG_CONFIRM_BTN)
        saved = True

    if add_to_chart:
        await page.click(selectors.PINE_EDITOR_ADD_TO_CHART_BTN)

    return {
        "slug": slug,
        "name": name,
        "saved": saved,
        "added_to_chart": add_to_chart,
        "code_loaded_chars": len(code or ""),
        "warnings": [],
    }


async def save_indicator(page: Any, name: str, code: str) -> dict:
    return await paste_pine(page, code=code, name=name, save=True, add_to_chart=False)


_STATS_EXTRACT_JS = """
() => {
    const rows = Array.from(document.querySelectorAll('[data-name="stats-row"]'));
    const out = {};
    for (const r of rows) {
        const k = (r.getAttribute('data-stat') || '').toLowerCase();
        const v = parseFloat((r.querySelector('[data-name="stat-value"]') || {}).textContent || '');
        if (!Number.isNaN(v)) out[k] = v;
    }
    return out;
}
"""


def _screenshot_dir() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    d = Path(base) / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def run_strategy_tester(
    page: Any,
    code: str | None = None,
    slug: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict:
    if symbol:
        from .chart import open_chart
        await open_chart(page, symbol, timeframe or "1h")

    paste_result = await paste_pine(
        page,
        code=code,
        slug=slug,
        name=(f"yt_strategy_{slug}" if slug else None),
        save=True,
        add_to_chart=True,
    )

    await page.click(selectors.STRATEGY_TESTER_TAB)
    await page.wait_for_selector(selectors.STRATEGY_TESTER_STATS_PANEL, timeout=15_000)

    stats_loc = page.locator(selectors.STRATEGY_TESTER_STATS_PANEL)
    stats = await stats_loc.evaluate(_STATS_EXTRACT_JS)

    report_loc = page.locator(selectors.STRATEGY_TESTER_REPORT_REGION)
    png = await report_loc.screenshot()
    ts = time.strftime("%Y-%m-%dT%H-%M-%S")
    label = slug or symbol or "strategy"
    path = _screenshot_dir() / f"{ts}-{label}-tester.png"
    path.write_bytes(png)

    return {
        "slug": slug,
        "symbol": symbols.normalize(symbol) if symbol else None,
        "timeframe": timeframe,
        "stats": stats,
        "screenshot_path": str(path),
        "screenshot_b64": base64.b64encode(png).decode("ascii"),
        "tv_pine_name": paste_result.get("name"),
        "warnings": [],
    }
