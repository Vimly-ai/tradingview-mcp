from __future__ import annotations

import pytest

from tradingview_mcp.core.services.tv_browser.exceptions import (
    TVSessionExpired,
    TVLoginTimeout,
    TVBrowserDead,
    TVRateLimit,
    TVCaptchaChallenge,
    TVSubscriptionRequired,
    TVLimitReached,
    TVClickIntercepted,
    TVDOMShapeChanged,
    TVPineCompileError,
)


def test_basic_exceptions_inherit_exception():
    for cls in (
        TVSessionExpired, TVLoginTimeout, TVBrowserDead,
        TVCaptchaChallenge, TVSubscriptionRequired,
        TVLimitReached, TVClickIntercepted,
    ):
        with pytest.raises(cls):
            raise cls("x")


def test_rate_limit_retry_after():
    e = TVRateLimit("rate-limited", retry_after_s=12.5)
    assert e.retry_after_s == 12.5
    e2 = TVRateLimit("no banner")
    assert e2.retry_after_s is None


def test_dom_shape_changed_panel():
    e = TVDOMShapeChanged("missing rows", panel="strategy_tester_stats")
    assert e.panel == "strategy_tester_stats"
    e2 = TVDOMShapeChanged("missing rows")
    assert e2.panel is None


def test_pine_compile_error_attributes():
    e = TVPineCompileError(
        "line 12: syntax error",
        full_text="line 12: syntax error at 'inpt.int'\nline 15: undefined",
        line=12,
    )
    assert str(e) == "line 12: syntax error"
    assert e.full_text.startswith("line 12")
    assert e.line == 12
    e2 = TVPineCompileError("oops", full_text="oops", line=None)
    assert e2.line is None
