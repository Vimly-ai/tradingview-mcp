"""Global min-interval async throttle.

Keeps TV's bot-detection comfortable. Singleton module-level timestamp;
concurrent callers serialize through an asyncio.Lock.
"""
from __future__ import annotations

import asyncio
import os
import time


_last_call_ts: float = 0.0
_lock = asyncio.Lock()


def _min_interval_s() -> float:
    try:
        return float(os.environ.get("TV_BROWSER_MIN_INTERVAL_MS", "500")) / 1000.0
    except ValueError:
        return 0.5


async def throttle() -> None:
    """Sleep until at least TV_BROWSER_MIN_INTERVAL_MS has elapsed since the
    previous call. Safe under concurrent callers — they serialize on a lock
    so the throttle is global rather than per-task."""
    global _last_call_ts
    async with _lock:
        now = time.monotonic()
        wait = _min_interval_s() - (now - _last_call_ts)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_ts = time.monotonic()
