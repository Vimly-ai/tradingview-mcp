"""Tests for tv_browser error envelope additions."""
from __future__ import annotations

from tradingview_mcp.core.errors import (
    ErrorCode,
    make_error,
    make_tv_browser_error,
    is_error,
)


def test_new_error_codes_exist():
    for name in (
        "TV_NOT_LOGGED_IN", "TV_LOGIN_TIMEOUT", "TV_BROWSER_DEAD",
        "TV_SELECTOR_NOT_FOUND", "TV_CLICK_INTERCEPTED",
        "TV_NAVIGATION_FAILED", "TV_PINE_COMPILE_ERROR",
        "TV_LIMIT_REACHED", "TV_SUBSCRIPTION_REQUIRED",
        "TV_RATE_LIMITED", "TV_CAPTCHA_CHALLENGE",
        "TV_DOM_SHAPE_CHANGED", "TV_UNEXPECTED_STATE",
    ):
        assert getattr(ErrorCode, name).value == name


def test_make_tv_browser_error_full_shape():
    env = make_tv_browser_error(
        code=ErrorCode.TV_SELECTOR_NOT_FOUND,
        message="Selector 'X' did not appear within 10s.",
        tool="tv_paste_pine",
        debug_artifacts_path="/tmp/debug/2026-06-07T12-00-00-tv_paste_pine/",
        retryable=False,
        hint="TV may have redesigned. Check selectors.py.",
        selector_name="X",
        selector_value="button[data-name='x']",
    )
    assert is_error(env)
    err = env["error"]
    assert err["code"] == "TV_SELECTOR_NOT_FOUND"
    assert err["error_type"] == "tv_browser"
    assert err["tool"] == "tv_paste_pine"
    assert err["debug_artifacts_path"].endswith("tv_paste_pine/")
    assert err["retryable"] is False
    assert err["hint"].startswith("TV may have")
    assert err["selector_name"] == "X"
    assert err["selector_value"].startswith("button[")


def test_make_tv_browser_error_default_hint():
    env = make_tv_browser_error(
        code=ErrorCode.TV_NOT_LOGGED_IN,
        message="TradingView session not active.",
    )
    err = env["error"]
    assert err["hint"]
    assert "tv_open_login_prompt" in err["hint"]


def test_default_hint_per_tv_code():
    for code in (
        ErrorCode.TV_NOT_LOGGED_IN, ErrorCode.TV_LOGIN_TIMEOUT,
        ErrorCode.TV_BROWSER_DEAD, ErrorCode.TV_SELECTOR_NOT_FOUND,
        ErrorCode.TV_CLICK_INTERCEPTED, ErrorCode.TV_NAVIGATION_FAILED,
        ErrorCode.TV_PINE_COMPILE_ERROR, ErrorCode.TV_LIMIT_REACHED,
        ErrorCode.TV_SUBSCRIPTION_REQUIRED, ErrorCode.TV_RATE_LIMITED,
        ErrorCode.TV_CAPTCHA_CHALLENGE, ErrorCode.TV_DOM_SHAPE_CHANGED,
    ):
        env = make_tv_browser_error(code=code, message="x")
        assert env["error"]["hint"], f"missing default hint for {code}"


def test_retryable_advisory_flag():
    yes = make_tv_browser_error(ErrorCode.TV_PINE_COMPILE_ERROR, "x", retryable=True)
    no = make_tv_browser_error(ErrorCode.TV_BROWSER_DEAD, "x", retryable=False)
    assert yes["error"]["retryable"] is True
    assert no["error"]["retryable"] is False
