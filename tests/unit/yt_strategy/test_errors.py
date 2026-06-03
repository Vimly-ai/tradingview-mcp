"""Tests for strategy-specific error envelope additions."""
from __future__ import annotations

from tradingview_mcp.core.errors import (
    ErrorCode,
    make_error,
    make_strategy_error,
    is_error,
)


def test_new_error_codes_exist():
    # These are added by this task.
    assert ErrorCode.STRATEGY_SECURITY_VIOLATION.value == "STRATEGY_SECURITY_VIOLATION"
    assert ErrorCode.STRATEGY_TIMEOUT.value == "STRATEGY_TIMEOUT"
    assert ErrorCode.STRATEGY_MEMORY_EXCEEDED.value == "STRATEGY_MEMORY_EXCEEDED"
    assert ErrorCode.STRATEGY_NO_TRADES.value == "STRATEGY_NO_TRADES"
    assert ErrorCode.STRATEGY_INVALID_CLASS.value == "STRATEGY_INVALID_CLASS"
    assert ErrorCode.STRATEGY_RUNTIME_ERROR.value == "STRATEGY_RUNTIME_ERROR"
    assert ErrorCode.TRANSCRIPT_UNAVAILABLE.value == "TRANSCRIPT_UNAVAILABLE"


def test_make_strategy_error_full_shape():
    env = make_strategy_error(
        code=ErrorCode.STRATEGY_RUNTIME_ERROR,
        message="name 'tslib' is not defined",
        user_code_line=23,
        user_code_snippet="    sma = tslib.SMA(self.data.Close, 20)",
        hint="Only 'backtesting', 'pandas', 'numpy', 'ta' are available.",
    )
    assert is_error(env)
    err = env["error"]
    assert err["code"] == "STRATEGY_RUNTIME_ERROR"
    assert err["message"] == "name 'tslib' is not defined"
    assert err["user_code_line"] == 23
    assert "tslib.SMA" in err["user_code_snippet"]
    assert err["hint"].startswith("Only")
    assert err["error_type"] == "strategy"


def test_make_strategy_error_null_line_for_timeout():
    env = make_strategy_error(
        code=ErrorCode.STRATEGY_TIMEOUT,
        message="Strategy did not converge within 60s.",
    )
    err = env["error"]
    assert err["user_code_line"] is None
    assert err["user_code_snippet"] is None
    assert err["hint"]  # default hint should be filled in


def test_default_hint_per_code():
    # Each strategy code has a canned hint when caller omits one.
    for code in (
        ErrorCode.STRATEGY_TIMEOUT,
        ErrorCode.STRATEGY_MEMORY_EXCEEDED,
        ErrorCode.STRATEGY_NO_TRADES,
        ErrorCode.STRATEGY_INVALID_CLASS,
    ):
        env = make_strategy_error(code=code, message="x")
        assert env["error"]["hint"], f"Missing default hint for {code}"
