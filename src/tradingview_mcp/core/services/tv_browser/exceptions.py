"""TV-specific exception classes raised inside tv_browser/.

Wrappers in server.py catch these and translate to make_tv_browser_error
envelopes per the §7.3 translation matrix in the design spec.
"""
from __future__ import annotations


class TVSessionExpired(Exception):
    """require_login found no logged-in session."""


class TVLoginTimeout(Exception):
    """interactive_login waited timeout_s without successful login."""


class TVBrowserDead(Exception):
    """Chromium crashed and auto-relaunch failed twice in a row."""


class TVRateLimit(Exception):
    """TradingView rate-limited the request (429 or visible banner)."""

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class TVCaptchaChallenge(Exception):
    """Cloudflare/TV bot-detection issued a captcha challenge."""


class TVSubscriptionRequired(Exception):
    """Action requires a paid TV plan."""


class TVLimitReached(Exception):
    """Plan ceiling hit (e.g. max alerts on Free tier)."""


class TVClickIntercepted(Exception):
    """Element existed but click was blocked, even after a re-dismiss attempt."""


class TVDOMShapeChanged(Exception):
    """Scraper found the panel but couldn't extract expected fields."""

    def __init__(self, message: str, panel: str | None = None) -> None:
        super().__init__(message)
        self.panel = panel


class TVPineCompileError(Exception):
    """TV's Pine compiler returned an error after paste; full panel text retained."""

    def __init__(self, message: str, full_text: str, line: int | None) -> None:
        super().__init__(message)
        self.full_text = full_text
        self.line = line
