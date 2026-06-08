"""
Structured error envelope and exception types for tradingview-mcp.

All recoverable failures return a typed error envelope:

    {"error": {"code": "<CODE>", "message": "<human-readable>", **extras}}

Use :func:`make_error` to construct envelopes and :func:`is_error` to check
them. Service layers may also raise typed exceptions (e.g.
:class:`BatchExecutionError`) which the MCP tool wrapper layer converts to the
same envelope shape so MCP clients see a uniform error API.

Migration notes
---------------
- Tools that adopt this format return ``dict`` (the envelope) on error and
  their normal type on success — the static return type becomes a union.
- Callers must check ``isinstance(result, dict) and "error" in result``
  instead of substring-matching previous ``{"error": "Analysis failed: ..."}``
  strings.
- Adoption is opt-in per tool; see PR notes for the current opt-in set.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Union


class ErrorCode(str, Enum):
    """Stable string codes for programmatic branching by MCP clients.

    Values are plain strings so they survive JSON serialization without
    extra encoding, and so they can be compared against literals like
    ``code == "ALL_BATCHES_FAILED"`` from any language.
    """

    # Input / validation
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    INVALID_EXCHANGE = "INVALID_EXCHANGE"
    INVALID_TIMEFRAME = "INVALID_TIMEFRAME"
    INVALID_PARAMETER = "INVALID_PARAMETER"

    # Upstream (TradingView / Yahoo / RSS feeds)
    UPSTREAM_RATE_LIMIT = "UPSTREAM_RATE_LIMIT"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    ALL_BATCHES_FAILED = "ALL_BATCHES_FAILED"

    # Data
    NO_DATA = "NO_DATA"
    PARTIAL_DATA = "PARTIAL_DATA"

    # Environment
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # Strategy code (LLM-generated user code) errors
    STRATEGY_SECURITY_VIOLATION = "STRATEGY_SECURITY_VIOLATION"
    STRATEGY_TIMEOUT = "STRATEGY_TIMEOUT"
    STRATEGY_MEMORY_EXCEEDED = "STRATEGY_MEMORY_EXCEEDED"
    STRATEGY_NO_TRADES = "STRATEGY_NO_TRADES"
    STRATEGY_INVALID_CLASS = "STRATEGY_INVALID_CLASS"
    STRATEGY_RUNTIME_ERROR = "STRATEGY_RUNTIME_ERROR"

    # YouTube / transcript
    TRANSCRIPT_UNAVAILABLE = "TRANSCRIPT_UNAVAILABLE"

    # TV browser-control errors (Phase 2)
    TV_NOT_LOGGED_IN = "TV_NOT_LOGGED_IN"
    TV_LOGIN_TIMEOUT = "TV_LOGIN_TIMEOUT"
    TV_BROWSER_DEAD = "TV_BROWSER_DEAD"
    TV_SELECTOR_NOT_FOUND = "TV_SELECTOR_NOT_FOUND"
    TV_CLICK_INTERCEPTED = "TV_CLICK_INTERCEPTED"
    TV_NAVIGATION_FAILED = "TV_NAVIGATION_FAILED"
    TV_PINE_COMPILE_ERROR = "TV_PINE_COMPILE_ERROR"
    TV_LIMIT_REACHED = "TV_LIMIT_REACHED"
    TV_SUBSCRIPTION_REQUIRED = "TV_SUBSCRIPTION_REQUIRED"
    TV_RATE_LIMITED = "TV_RATE_LIMITED"
    TV_CAPTCHA_CHALLENGE = "TV_CAPTCHA_CHALLENGE"
    TV_DOM_SHAPE_CHANGED = "TV_DOM_SHAPE_CHANGED"
    TV_UNEXPECTED_STATE = "TV_UNEXPECTED_STATE"


def make_error(code: Union[ErrorCode, str], message: str, **extra: Any) -> dict[str, Any]:
    """Construct a structured error envelope.

    Args:
        code: An :class:`ErrorCode` value or its raw string form. Accepting
            plain strings keeps the helper usable from code that doesn't want
            to import the enum (and from external contributions adopting the
            envelope shape).
        message: Human-readable description suitable for showing to a user.
        **extra: Additional structured fields — e.g. ``retry_after_s=30``,
            ``batches_attempted=5``, ``first_error="..."``, ``symbol="AAPL"``.

    Returns:
        ``{"error": {"code": ..., "message": ..., **extra}}``
    """
    code_str = code.value if isinstance(code, ErrorCode) else str(code)
    err: dict[str, Any] = {"code": code_str, "message": message}
    if extra:
        err.update(extra)
    return {"error": err}


def is_error(payload: Any) -> bool:
    """True if *payload* is an error envelope produced by :func:`make_error`.

    Checks both the outer ``"error"`` key and the inner ``"code"`` to avoid
    false positives against legacy string-error payloads (which had
    ``payload["error"]`` as a string, not a dict).
    """
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("error"), dict)
        and "code" in payload["error"]
    )


class BatchExecutionError(Exception):
    """Raised by batched scanners when every batch failed.

    The service layer raises this so the MCP tool wrapper at the boundary
    can convert it to an :func:`make_error` envelope with full context.
    Callers must not swallow it silently — that defeats the whole point of
    the sentinel.

    Attributes:
        batches_attempted: How many batches were issued to upstream.
        batches_failed: How many of those failed
            (equals ``batches_attempted`` whenever this is raised).
        first_error: ``repr()`` of the first exception observed across the
            batch loop, kept verbatim for debugging.
    """

    def __init__(
        self,
        batches_attempted: int,
        batches_failed: int,
        first_error: str,
    ) -> None:
        super().__init__(
            f"All {batches_attempted} batches failed; first error: {first_error}"
        )
        self.batches_attempted = batches_attempted
        self.batches_failed = batches_failed
        self.first_error = first_error


_TV_BROWSER_DEFAULT_HINTS: dict[str, str] = {
    "TV_NOT_LOGGED_IN": (
        "TradingView session not active. Call tv_open_login_prompt() to start "
        "the login flow."
    ),
    "TV_LOGIN_TIMEOUT": (
        "Login window timed out. Call tv_open_login_prompt() to try again."
    ),
    "TV_BROWSER_DEAD": (
        "Chromium could not be restarted. Inspect debug_artifacts_path; you "
        "may need to delete ~/.tradingview_mcp_data/browser/ if the profile "
        "is corrupt."
    ),
    "TV_SELECTOR_NOT_FOUND": (
        "TradingView may have changed the DOM. Check "
        "tv_browser/selectors.py and the debug screenshot."
    ),
    "TV_CLICK_INTERCEPTED": (
        "An undocumented overlay is blocking the click. Manual intervention "
        "may be needed."
    ),
    "TV_NAVIGATION_FAILED": (
        "Page navigation failed. Check network connection or tradingview.com "
        "status."
    ),
    "TV_PINE_COMPILE_ERROR": (
        "Pine script did not compile. Fix the code and retry; the strategy "
        "was NOT saved."
    ),
    "TV_LIMIT_REACHED": (
        "TradingView refused due to a plan ceiling. Delete an existing "
        "alert/indicator to free a slot."
    ),
    "TV_SUBSCRIPTION_REQUIRED": (
        "This feature requires a paid TradingView plan."
    ),
    "TV_RATE_LIMITED": (
        "TradingView rate-limited the request. Wait and retry."
    ),
    "TV_CAPTCHA_CHALLENGE": (
        "A captcha appeared in the visible browser. Solve it then retry."
    ),
    "TV_DOM_SHAPE_CHANGED": (
        "Scraper found the panel but couldn't extract expected fields. "
        "TV may have changed the panel structure."
    ),
    "TV_UNEXPECTED_STATE": (
        "Page is in a state we didn't anticipate. Inspect debug artifacts."
    ),
}


def make_tv_browser_error(
    code: ErrorCode | str,
    message: str,
    tool: str | None = None,
    debug_artifacts_path: str | None = None,
    retryable: bool = False,
    hint: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Construct a tv_browser-error envelope.

    Adds ``error_type="tv_browser"`` to the inner dict so the assistant
    can branch on category. Fills in a default hint when none is supplied.
    """
    code_str = code.value if isinstance(code, ErrorCode) else str(code)
    return make_error(
        code,
        message,
        error_type="tv_browser",
        tool=tool,
        debug_artifacts_path=debug_artifacts_path,
        retryable=retryable,
        hint=hint if hint is not None else _TV_BROWSER_DEFAULT_HINTS.get(code_str, ""),
        **extra,
    )


_STRATEGY_DEFAULT_HINTS: dict[str, str] = {
    "STRATEGY_TIMEOUT": (
        "Strategy did not converge within the wall-clock limit. Check for "
        "infinite loops or O(n^2) logic over bar history."
    ),
    "STRATEGY_MEMORY_EXCEEDED": (
        "Strategy used more memory than allowed. Avoid storing per-bar arrays; "
        "use self.data slicing instead."
    ),
    "STRATEGY_NO_TRADES": (
        "Strategy produced 0 trades. Entry/exit conditions may never both fire. "
        "Check signal logic and indicator initialization."
    ),
    "STRATEGY_INVALID_CLASS": (
        "Code must define a class subclassing backtesting.Strategy."
    ),
    "STRATEGY_SECURITY_VIOLATION": (
        "Code referenced a forbidden name. Only 'backtesting', 'pandas', "
        "'numpy', 'ta', 'math', 'statistics' are available."
    ),
    "STRATEGY_RUNTIME_ERROR": (
        "Strategy raised a runtime exception. See user_code_line and "
        "user_code_snippet for the failure location."
    ),
}


def make_strategy_error(
    code: ErrorCode | str,
    message: str,
    user_code_line: int | None = None,
    user_code_snippet: str | None = None,
    hint: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Construct a strategy-error envelope with the canonical fields.

    Adds ``error_type="strategy"`` to the inner dict so the assistant can
    branch on category without parsing the code. Fills in a default hint
    when none is supplied.
    """
    code_str = code.value if isinstance(code, ErrorCode) else str(code)
    return make_error(
        code,
        message,
        error_type="strategy",
        user_code_line=user_code_line,
        user_code_snippet=user_code_snippet,
        hint=hint if hint is not None else _STRATEGY_DEFAULT_HINTS.get(code_str, ""),
        **extra,
    )
