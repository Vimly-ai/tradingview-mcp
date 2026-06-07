from __future__ import annotations

import asyncio
import time

import pytest

from tradingview_mcp.core.services.tv_browser import throttle as throttle_mod


@pytest.fixture(autouse=True)
def _reset_throttle():
    throttle_mod._last_call_ts = 0.0
    yield
    throttle_mod._last_call_ts = 0.0


async def test_first_call_does_not_sleep(monkeypatch):
    monkeypatch.setenv("TV_BROWSER_MIN_INTERVAL_MS", "100")
    t0 = time.monotonic()
    await throttle_mod.throttle()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.05


async def test_second_call_waits_for_interval(monkeypatch):
    monkeypatch.setenv("TV_BROWSER_MIN_INTERVAL_MS", "100")
    await throttle_mod.throttle()
    t0 = time.monotonic()
    await throttle_mod.throttle()
    elapsed = time.monotonic() - t0
    assert 0.09 <= elapsed <= 0.2, f"expected ~100ms wait, got {elapsed:.3f}s"


async def test_after_long_idle_no_wait(monkeypatch):
    monkeypatch.setenv("TV_BROWSER_MIN_INTERVAL_MS", "100")
    throttle_mod._last_call_ts = time.monotonic() - 5.0
    t0 = time.monotonic()
    await throttle_mod.throttle()
    assert time.monotonic() - t0 < 0.05


async def test_concurrent_calls_serialize(monkeypatch):
    monkeypatch.setenv("TV_BROWSER_MIN_INTERVAL_MS", "50")
    t0 = time.monotonic()
    await asyncio.gather(
        throttle_mod.throttle(),
        throttle_mod.throttle(),
        throttle_mod.throttle(),
    )
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.09, f"expected ≥90ms total, got {elapsed:.3f}s"
