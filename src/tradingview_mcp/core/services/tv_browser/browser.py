"""Persistent Chromium lifecycle for tv_browser tools.

One Chromium instance per MCP-server lifetime. Asyncio mutex serializes
all tool calls. Idle timer auto-closes after TV_BROWSER_IDLE_S of
inactivity, but defers while the lock is held and is fully disabled
during interactive_login. Crash recovery relaunches once on dead state;
a second consecutive failure raises TVBrowserDead.
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from playwright.async_api import async_playwright  # type: ignore

from .exceptions import TVBrowserDead


def _user_data_dir() -> str:
    return os.environ.get(
        "TV_BROWSER_USER_DATA_DIR",
        os.path.expanduser("~/.tradingview_mcp_data/browser"),
    )


def _headless() -> bool:
    return os.environ.get("TV_BROWSER_HEADLESS", "false").lower() in ("true", "1", "yes")


def _idle_s() -> float:
    try:
        return float(os.environ.get("TV_BROWSER_IDLE_S", "300"))
    except ValueError:
        return 300.0


class TVBrowser:
    """Singleton holder for the persistent Chromium context."""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._lock = asyncio.Lock()
        self._idle_disabled = False
        self._last_activity = time.monotonic()
        self._idle_task: asyncio.Task | None = None  # type: ignore[type-arg]

    async def get_page(self) -> Any:
        """Return the live Page, lazily launching or relaunching if needed."""
        try:
            if not await self._is_alive_internal():
                await self._dispose()
                await self._launch()
        except Exception as first_err:
            await self._dispose()
            try:
                await self._launch()
            except Exception as second_err:
                raise TVBrowserDead(
                    f"Two consecutive launch failures: {first_err!r}; {second_err!r}"
                ) from second_err
        self._touch()
        return self._page

    async def shutdown(self) -> None:
        await self._dispose()

    async def is_alive(self) -> bool:
        return await self._is_alive_internal()

    async def disable_idle(self) -> None:
        self._idle_disabled = True

    async def enable_idle(self) -> None:
        self._idle_disabled = False
        self._touch()

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    async def _launch(self) -> None:
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=_user_data_dir(),
            headless=_headless(),
            viewport={"width": 1600, "height": 1000},
        )
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )
        self._start_idle_task()

    async def _dispose(self) -> None:
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            try:
                await self._idle_task
            except (asyncio.CancelledError, Exception):
                pass
        self._idle_task = None
        try:
            if self._context is not None:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._page = None
        self._playwright = None

    async def _is_alive_internal(self) -> bool:
        if self._page is None or self._context is None:
            return False
        try:
            if self._page.is_closed():
                return False
            if hasattr(self._context, "browser"):
                browser = self._context.browser
                if browser is not None and hasattr(browser, "is_connected"):
                    if not browser.is_connected():
                        return False
        except Exception:
            return False
        return True

    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    def _start_idle_task(self) -> None:
        if self._idle_task is not None and not self._idle_task.done():
            return
        loop = asyncio.get_event_loop()
        self._idle_task = loop.create_task(self._idle_watchdog())

    async def _idle_watchdog(self) -> None:
        check_every = max(0.05, _idle_s() / 10)
        while True:
            await asyncio.sleep(check_every)
            if self._idle_disabled:
                continue
            if self._lock.locked():
                continue
            if (time.monotonic() - self._last_activity) >= _idle_s():
                await self._dispose()
                return


# --- module-level singleton --------------------------------------------------

_instance: TVBrowser | None = None


def _get_singleton() -> TVBrowser:
    global _instance
    if _instance is None:
        _instance = TVBrowser()
    return _instance


def reset_singleton() -> None:
    """Test helper — drop the singleton so each test starts clean."""
    global _instance
    if _instance is not None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In async tests we can't run_until_complete; best-effort cleanup
                pass
            else:
                loop.run_until_complete(_instance._dispose())
        except Exception:
            pass
    _instance = None


@asynccontextmanager
async def page_lock() -> AsyncIterator[Any]:
    """`async with page_lock() as page:` — serializes tool calls on the singleton."""
    inst = _get_singleton()
    async with inst.lock:
        page = await inst.get_page()
        try:
            yield page
        finally:
            inst._touch()
