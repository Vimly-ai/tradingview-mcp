"""Idempotent modal-dismissal pre-pass.

TradingView throws modals constantly (save prompts, upgrade banners,
"are you sure" dialogs). One stale modal blocks every subsequent click,
so we sweep them all before any tool action.
"""
from __future__ import annotations

from typing import Any

from .selectors import MODAL_DISMISS_SELECTORS


async def dismiss_modals(page: Any, timeout_s: float = 1.0) -> int:
    """For each selector in MODAL_DISMISS_SELECTORS, try one click with a short timeout.

    Returns the count of modals dismissed. Per-selector errors are swallowed
    silently — the next tool action will surface a more specific error if a
    blocking modal slipped through.
    """
    dismissed = 0
    for sel in MODAL_DISMISS_SELECTORS:
        try:
            loc = page.locator(sel)
            await loc.wait_for(state="visible", timeout=timeout_s * 1000)
            await loc.click(timeout=int(timeout_s * 1000))
            dismissed += 1
        except Exception:
            continue
    return dismissed
