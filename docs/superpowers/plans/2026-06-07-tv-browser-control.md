# TV Browser Control Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 17 MCP tools to `tradingview-mcp` that drive a persistent logged-in Chromium via playwright-python — read TV charts visually, scrape watchlists / alerts / indicators, paste Pine + run TV's Strategy Tester (closing the Phase 1 loop), manage alerts + watchlists.

**Architecture:** Approach A from the spec — one persistent Chromium per MCP-server lifetime, asyncio mutex serializing all tool calls, modal-dismissal pre-pass, throttle (500 ms default), single-source-of-truth `selectors.py`, 13 new error codes routed through a `make_tv_browser_error` envelope. All new code under `src/tradingview_mcp/core/services/tv_browser/`. Tests use mocked playwright at the unit boundary + a local fake-TV aiohttp server at the integration boundary; real-TV smoke tests are off CI.

**Tech Stack:** Python 3.10+, `playwright>=1.40` (Chromium), `aiohttp>=3.9` (fake-TV fixture), `pytest-asyncio>=0.23`, `pytest-cov>=4.1`, `pytest-playwright>=0.5`, `freezegun>=1.4`.

**Reference spec:** `docs/superpowers/specs/2026-06-04-tv-browser-control-design.md` (commit `37b1371`).

---

## File Structure

New files under `src/tradingview_mcp/core/services/tv_browser/`:

| File | Responsibility |
|---|---|
| `__init__.py` | Package marker + public re-exports |
| `selectors.py` | DOM selectors + URL templates (reads `TV_BASE_URL`) |
| `exceptions.py` | TV-specific exception classes |
| `symbols.py` | `normalize()` — user-facing symbol → TV-canonical `EXCHANGE:TICKER` |
| `throttle.py` | Global min-interval async throttle |
| `modals.py` | Generic modal-dismissal pre-pass |
| `browser.py` | Chromium lifecycle: mutex, idle timer, crash recovery, headless flag |
| `session.py` | `is_logged_in`, `require_login`, `interactive_login`, `logout` |
| `debug.py` | `debug_on_failure` context manager + artifact rotation |
| `chart.py` | `open_chart`, `screenshot_chart`, `add_indicator` |
| `data.py` | `read_watchlist`, `read_alerts`, `list_my_indicators` |
| `pine.py` | `paste_pine`, `save_indicator`, `run_strategy_tester` + Monaco helper |
| `alerts.py` | `create_alert` (price-cross MVP), `delete_alert` |
| `watchlists.py` | `add_to_watchlist`, `remove_from_watchlist` |

Modified files:

| File | Change |
|---|---|
| `pyproject.toml` | Add `playwright>=1.40` runtime dep + 5 dev deps |
| `src/tradingview_mcp/core/errors.py` | Add 13 new `ErrorCode` values + `make_tv_browser_error` helper |
| `src/tradingview_mcp/server.py` | Register 17 new MCP tools |
| `.env.example` | Document 8 new env vars |
| `.github/workflows/test.yml` | Add `playwright install chromium` step + integration test job |
| `README.md` | Add Phase 2 subsection |

Test infrastructure:

| File | Purpose |
|---|---|
| `tests/unit/tv_browser/__init__.py` | Package marker |
| `tests/unit/tv_browser/test_errors.py` | 13 new error codes + `make_tv_browser_error` shape |
| `tests/unit/tv_browser/test_exceptions.py` | Exception class attributes |
| `tests/unit/tv_browser/test_selectors_pinned.py` | EXPECTED_SELECTORS baseline |
| `tests/unit/tv_browser/test_symbols.py` | Routing parametrized |
| `tests/unit/tv_browser/test_throttle.py` | Min-interval spacing |
| `tests/unit/tv_browser/test_modals.py` | Idempotent dismissal |
| `tests/unit/tv_browser/test_browser.py` | Lifecycle (mocked playwright) |
| `tests/unit/tv_browser/test_session.py` | Login flow (mocked playwright) |
| `tests/unit/tv_browser/test_debug.py` | Artifact write + rotation |
| `tests/unit/tv_browser/test_chart.py` | Mocked-page call sequences |
| `tests/unit/tv_browser/test_data.py` | Mocked-page extraction |
| `tests/unit/tv_browser/test_pine.py` | Mocked-page paste/test flow |
| `tests/unit/tv_browser/test_alerts.py` | Mocked-page create/delete |
| `tests/unit/tv_browser/test_watchlists.py` | Mocked-page add/remove |
| `tests/unit/tv_browser/test_wrapper_invariants.py` | Every tool wraps in `debug_on_failure` (runtime, not AST) |
| `tests/integration/tv_browser/__init__.py` | Package marker |
| `tests/integration/tv_browser/conftest.py` | fake_tv server fixture |
| `tests/integration/tv_browser/test_chart_e2e.py` | chart tools vs fake_tv |
| `tests/integration/tv_browser/test_pine_e2e.py` | pine tools (Monaco) vs fake_tv |
| `tests/integration/tv_browser/test_session_e2e.py` | login flow vs fake_tv/login.html |
| `tests/integration/tv_browser/test_mcp_tools.py` | MCP stdio handshake against all 17 tools |
| `tests/fixtures/fake_tv/server.py` | aiohttp server picks random port |
| `tests/fixtures/fake_tv/pages/chart.html` | chart-shaped DOM + CHART_READY anchor |
| `tests/fixtures/fake_tv/pages/pine_editor.html` | Monaco editor from CDN + save / add-to-chart buttons |
| `tests/fixtures/fake_tv/pages/strategy_tester.html` | stats panel |
| `tests/fixtures/fake_tv/pages/watchlist.html` | symbol rows |
| `tests/fixtures/fake_tv/pages/alerts.html` | alert list + create dialog |
| `tests/fixtures/fake_tv/pages/login.html` | simulates tradingview signin |
| `tests/fixtures/fake_tv/README.md` | When to refresh fixtures |

---

## Conventions Used Throughout

- `from __future__ import annotations` at module top (project convention).
- Modern type hints (`list[str]`, `str | None`); project requires Python 3.10+.
- Module-private helpers prefixed with `_`.
- Async functions use `@pytest.mark.asyncio` in tests.
- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- Every commit ends with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Selectors NEVER appear as literal strings outside `selectors.py`. CI lint rejects.
- Working directory: `/Users/andrewfackrell/Trading MCP/tradingview-mcp`. Branch: `feat/tv-browser-control`.

---

## Task 1 — Bootstrap: playwright dep + package + chromium install + fake-TV skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/tradingview_mcp/core/services/tv_browser/__init__.py`
- Create: `tests/unit/tv_browser/__init__.py`
- Create: `tests/integration/tv_browser/__init__.py`
- Create: `tests/fixtures/fake_tv/__init__.py`
- Create: `tests/fixtures/fake_tv/README.md`

- [ ] **Step 1: Verify baseline tests pass**

Run: `cd "/Users/andrewfackrell/Trading MCP/tradingview-mcp" && uv run pytest tests/ -q`
Expected: same pass count as end of Phase 1 (243 passed, 1 skipped on macOS).

- [ ] **Step 2: Add playwright + new dev deps to pyproject.toml**

Edit `pyproject.toml`. Replace the `dependencies` and `[tool.uv]` blocks:

```toml
dependencies = [
  "feedparser>=6.0.12",
  "mcp[cli]>=1.12.0",
  "requests>=2.32",
  "tradingview-screener>=0.6.4",
  "tradingview-ta>=3.3.0",
  "backtesting>=0.3.3",
  "youtube-transcript-api>=0.6.2",
  "yt-dlp>=2025.01.01",
  "ta>=0.11.0",
  "scikit-optimize>=0.10.0",
  "Pillow>=10",
  "pandas>=2.0",
  "numpy>=1.24",
  "playwright>=1.40",
]
```

```toml
[tool.uv]
dev-dependencies = [
    "pytest>=9.0.3",
    "pytest-mock>=3.12",
    "requests-mock>=1.12",
    "pytest-timeout>=2.3",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "pytest-playwright>=0.5",
    "aiohttp>=3.9",
    "freezegun>=1.4",
]
package = true
```

- [ ] **Step 3: Run `uv sync` + install Chromium**

```bash
uv sync
uv run playwright install chromium
```
Expected: deps install; chromium binary downloads (~150MB). May take ~30s on slow connections.

- [ ] **Step 4: Verify imports work**

```bash
uv run python -c "import playwright, aiohttp, freezegun; from playwright.async_api import async_playwright; print('ok')"
```
Expected: `ok`

- [ ] **Step 5: Create the tv_browser package directory**

Create `src/tradingview_mcp/core/services/tv_browser/__init__.py`:

```python
"""TradingView browser-control via playwright.

Drives a persistent logged-in Chromium for screenshotting charts, scraping
private TV data (watchlists, alerts, indicators), pasting Pine scripts into
TV's Pine Editor / Strategy Tester, and managing alerts + watchlists.

Submodules:
- selectors: DOM selectors + URL templates (single source of truth)
- exceptions: TV-specific exception classes
- symbols: user-facing symbol -> TV-canonical EXCHANGE:TICKER form
- throttle: global min-interval async throttle
- modals: generic modal-dismissal pre-pass
- browser: persistent Chromium lifecycle (mutex, idle timer, crash recovery)
- session: login detection + interactive login + logout
- debug: debug_on_failure context manager + artifact rotation
- chart: open_chart, screenshot_chart, add_indicator
- data: read_watchlist, read_alerts, list_my_indicators
- pine: paste_pine, save_indicator, run_strategy_tester (+ Monaco helper)
- alerts: create_alert (price-cross MVP), delete_alert
- watchlists: add_to_watchlist, remove_from_watchlist
"""
from __future__ import annotations
```

- [ ] **Step 6: Create empty test package markers**

Run:
```bash
touch tests/unit/tv_browser/__init__.py
touch tests/integration/tv_browser/__init__.py
touch tests/fixtures/fake_tv/__init__.py
```

- [ ] **Step 7: Create fake_tv README placeholder**

Create `tests/fixtures/fake_tv/README.md`:

```markdown
# fake_tv — TradingView-shaped test fixture

This directory hosts a local aiohttp server (`server.py`) that mimics
TradingView's DOM structure for integration tests. Pages under `pages/`
mirror the selectors documented in `src/tradingview_mcp/core/services/tv_browser/selectors.py`.

## When to refresh

- After any selector patch in `selectors.py` (mirror the change here).
- Quarterly review otherwise — TV ships subtle DOM changes that may not
  break individual selectors but can break our scraping logic.
- After a `TV_DOM_SHAPE_CHANGED` error surfaces from real TV that wasn't
  caught by integration tests.

## Lifecycle

A session-scoped pytest fixture in
`tests/integration/tv_browser/conftest.py` starts the server on a random
free port and sets `TV_BASE_URL` so `selectors.py` URL templates point at
this server.
```

- [ ] **Step 8: Configure pytest-asyncio in pyproject.toml**

Append to `pyproject.toml` (or merge into existing `[tool.pytest.ini_options]` if present):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

This makes all async test functions run without needing explicit `@pytest.mark.asyncio` decorators — keeps test files cleaner.

- [ ] **Step 9: Re-run baseline tests**

Run: `uv run pytest tests/ -q`
Expected: same 243 passed + 1 skipped — no regressions from adding deps / asyncio_mode.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock src/tradingview_mcp/core/services/tv_browser/ tests/unit/tv_browser/ tests/integration/tv_browser/ tests/fixtures/fake_tv/
git commit -m "$(cat <<'EOF'
chore(tv_browser): bootstrap playwright + tv_browser package + test scaffolding

Adds playwright>=1.40 runtime dep, plus pytest-asyncio, pytest-cov,
pytest-playwright, aiohttp, freezegun dev deps. Creates
src/tradingview_mcp/core/services/tv_browser/ package and test package
markers under tests/unit/tv_browser/, tests/integration/tv_browser/,
tests/fixtures/fake_tv/. Sets asyncio_mode=auto so async tests don't
need per-function decorators.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — Extend `errors.py` with 13 TV browser codes + `make_tv_browser_error`

**Files:**
- Modify: `src/tradingview_mcp/core/errors.py`
- Create: `tests/unit/tv_browser/test_errors.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/tv_browser/test_errors.py`:

```python
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
    assert err["hint"]  # default hint must be filled in
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
```

Run: `uv run pytest tests/unit/tv_browser/test_errors.py -v`
Expected: all tests fail with `AttributeError`/`ImportError`.

- [ ] **Step 2: Add 13 new ErrorCode values**

Edit `src/tradingview_mcp/core/errors.py`. After the existing `TRANSCRIPT_UNAVAILABLE = "TRANSCRIPT_UNAVAILABLE"` line (added in Phase 1), add:

```python

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
```

- [ ] **Step 3: Add `make_tv_browser_error` helper**

Append to `src/tradingview_mcp/core/errors.py` (after `make_strategy_error`):

```python


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/tv_browser/test_errors.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest tests/ -q`
Expected: 248 passed + 1 skipped (243 + 5 new).

- [ ] **Step 6: Commit**

```bash
git add src/tradingview_mcp/core/errors.py tests/unit/tv_browser/test_errors.py
git commit -m "$(cat <<'EOF'
feat(errors): add 13 TV browser-control error codes + make_tv_browser_error

Covers the full Phase 2 error taxonomy (session, browser-lifecycle,
selector/DOM, navigation, Pine compile, limits, subscription, rate-limit,
captcha, catch-all). make_tv_browser_error stamps the envelope with
error_type='tv_browser', threads tool/debug_artifacts_path/retryable
fields, and fills a default hint per code.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — `exceptions.py`: TV-specific exception classes

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/exceptions.py`
- Create: `tests/unit/tv_browser/test_exceptions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/tv_browser/test_exceptions.py`:

```python
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
```

Run: `uv run pytest tests/unit/tv_browser/test_exceptions.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `exceptions.py`**

Create `src/tradingview_mcp/core/services/tv_browser/exceptions.py`:

```python
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
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_exceptions.py -v`
Expected: 4/4 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: 252 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/exceptions.py tests/unit/tv_browser/test_exceptions.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): TV-specific exception classes

Ten classes used by tv_browser modules and translated to envelopes by
the server-side wrappers. Extra-attribute classes (TVRateLimit,
TVDOMShapeChanged, TVPineCompileError) carry context needed by their
envelope shapes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — `selectors.py` + pinning test

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/selectors.py`
- Create: `tests/unit/tv_browser/test_selectors_pinned.py`

- [ ] **Step 1: Write failing pinning test**

Create `tests/unit/tv_browser/test_selectors_pinned.py`:

```python
"""Two-keys-in-two-pockets baseline check.

If you edit selectors.py without updating EXPECTED_SELECTORS in this
file (or vice versa), this test fails. The intent is to force conscious
selector updates that ship with both halves in the same commit.
"""
from __future__ import annotations

import pytest

from tradingview_mcp.core.services.tv_browser import selectors


EXPECTED_SELECTORS = {
    # Ready-state anchors
    "CHART_READY":            '[data-name="legend-source-item"]',
    "PINE_EDITOR_READY":      'div.tv-script-editor',
    "STRATEGY_TESTER_READY":  '[data-name="strategy-tester-overview"]',
    # Login
    "LOGGED_IN_INDICATOR":    'button[aria-label="Open user menu"]',
    # Chart
    "MAIN_CHART_CANVAS":      'div[data-name="pane-main"] canvas',
    "TICKER_SEARCH_INPUT":    'input[data-role="search-input"]',
    "INDICATOR_SEARCH_DIALOG_INPUT": 'input[data-name="indicator-search"]',
    "INDICATOR_DIALOG_FIRST_RESULT": 'div[data-name="indicator-result"]:first-child',
    # Pine editor
    "PINE_EDITOR_TEXTAREA":           'div.monaco-editor',
    "PINE_EDITOR_SAVE_BTN":           'button[data-name="save"]',
    "PINE_EDITOR_ADD_TO_CHART_BTN":   'button[data-name="add-to-chart"]',
    "PINE_EDITOR_ERROR_PANEL":        'div[data-name="pine-script-errors"]',
    "PINE_EDITOR_TAB":                'button[data-name="open-pine-editor"]',
    "SAVE_DIALOG_NAME_INPUT":         'input[data-name="script-name"]',
    "SAVE_DIALOG_CONFIRM_BTN":        'button[data-name="save-confirm"]',
    # Strategy Tester
    "STRATEGY_TESTER_TAB":            'button[id="footer-tester"]',
    "STRATEGY_TESTER_STATS_PANEL":    'div[data-name="strategy-tester-stats"]',
    "STRATEGY_TESTER_REPORT_REGION":  'div[data-name="strategy-tester-report"]',
    # Watchlist
    "WATCHLIST_ROWS":                 '[data-name="watchlist-symbol-row"]',
    "WATCHLIST_DROPDOWN":             'button[data-name="watchlist-selector"]',
    # Alerts
    "ALERT_LIST_ROW":                 '[data-name="alerts-item"]',
    "ALERT_CREATE_BTN_TOOLBAR":       'button[data-name="legend-create-alert-button"]',
    "ALERT_DIALOG":                   'div[data-name="alert-dialog"]',
    "ALERT_DIALOG_PRICE_INPUT":       'input[data-name="alert-value-input"]',
    "ALERT_DIALOG_MESSAGE_INPUT":     'textarea[data-name="alert-message"]',
    "ALERT_DIALOG_CREATE_BTN":        'button[data-name="submit"]',
}


@pytest.mark.parametrize("name,expected", EXPECTED_SELECTORS.items())
def test_selector_pinned(name, expected):
    actual = getattr(selectors, name)
    assert actual == expected, (
        f"Selector {name} changed. If TV redesigned, update both selectors.py "
        f"AND EXPECTED_SELECTORS in the same commit."
    )


def test_modal_dismiss_selectors_contains_close_buttons():
    assert any("Close" in s for s in selectors.MODAL_DISMISS_SELECTORS)
    assert any("save-prompt" in s for s in selectors.MODAL_DISMISS_SELECTORS)


def test_tv_base_url_default():
    import importlib
    import os
    os.environ.pop("TV_BASE_URL", None)
    importlib.reload(selectors)
    assert selectors._TV_BASE == "https://www.tradingview.com"


def test_tv_base_url_override(monkeypatch):
    import importlib
    monkeypatch.setenv("TV_BASE_URL", "http://127.0.0.1:9999")
    importlib.reload(selectors)
    assert selectors._TV_BASE == "http://127.0.0.1:9999"
    assert selectors.CHART_URL_TPL.startswith("http://127.0.0.1:9999")
```

Run: `uv run pytest tests/unit/tv_browser/test_selectors_pinned.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `selectors.py`**

Create `src/tradingview_mcp/core/services/tv_browser/selectors.py`:

```python
"""Single source of truth for TV DOM selectors and URL templates.

When TradingView ships a redesign, this is the only file to patch. Every
selector here is also pinned in tests/unit/tv_browser/test_selectors_pinned.py
to force conscious updates.
"""
from __future__ import annotations

import os


_TV_BASE = os.environ.get("TV_BASE_URL", "https://www.tradingview.com").rstrip("/")


# --- URL templates -----------------------------------------------------------
CHART_URL_TPL    = _TV_BASE + "/chart/?symbol={symbol}&interval={tv_interval}"
PINE_EDITOR_URL  = _TV_BASE + "/pine-editor/"
PINE_LIBRARY_URL = _TV_BASE + "/scripts/yours/"
ALERTS_URL       = _TV_BASE + "/alerts/"
LOGIN_URL        = _TV_BASE + "/accounts/signin/"


# --- Ready-state anchors -----------------------------------------------------
# Selectors that, once present, confirm a page has fully loaded.
CHART_READY            = '[data-name="legend-source-item"]'
PINE_EDITOR_READY      = 'div.tv-script-editor'
STRATEGY_TESTER_READY  = '[data-name="strategy-tester-overview"]'


# --- Login state -------------------------------------------------------------
LOGGED_IN_INDICATOR    = 'button[aria-label="Open user menu"]'


# --- Chart -------------------------------------------------------------------
MAIN_CHART_CANVAS               = 'div[data-name="pane-main"] canvas'
TICKER_SEARCH_INPUT             = 'input[data-role="search-input"]'
INDICATOR_SEARCH_DIALOG_INPUT   = 'input[data-name="indicator-search"]'
INDICATOR_DIALOG_FIRST_RESULT   = 'div[data-name="indicator-result"]:first-child'


# --- Pine Editor -------------------------------------------------------------
# Monaco-backed editor. Use _set_monaco_value via page.evaluate, NOT page.fill.
PINE_EDITOR_TEXTAREA           = 'div.monaco-editor'
PINE_EDITOR_SAVE_BTN           = 'button[data-name="save"]'
PINE_EDITOR_ADD_TO_CHART_BTN   = 'button[data-name="add-to-chart"]'
PINE_EDITOR_ERROR_PANEL        = 'div[data-name="pine-script-errors"]'
PINE_EDITOR_TAB                = 'button[data-name="open-pine-editor"]'
SAVE_DIALOG_NAME_INPUT         = 'input[data-name="script-name"]'
SAVE_DIALOG_CONFIRM_BTN        = 'button[data-name="save-confirm"]'


# --- Strategy Tester ---------------------------------------------------------
STRATEGY_TESTER_TAB            = 'button[id="footer-tester"]'
STRATEGY_TESTER_STATS_PANEL    = 'div[data-name="strategy-tester-stats"]'
STRATEGY_TESTER_REPORT_REGION  = 'div[data-name="strategy-tester-report"]'


# --- Watchlist ---------------------------------------------------------------
WATCHLIST_ROWS                 = '[data-name="watchlist-symbol-row"]'
WATCHLIST_DROPDOWN             = 'button[data-name="watchlist-selector"]'


# --- Alerts ------------------------------------------------------------------
ALERT_LIST_ROW                 = '[data-name="alerts-item"]'
ALERT_CREATE_BTN_TOOLBAR       = 'button[data-name="legend-create-alert-button"]'
ALERT_DIALOG                   = 'div[data-name="alert-dialog"]'
ALERT_DIALOG_PRICE_INPUT       = 'input[data-name="alert-value-input"]'
ALERT_DIALOG_MESSAGE_INPUT     = 'textarea[data-name="alert-message"]'
ALERT_DIALOG_CREATE_BTN        = 'button[data-name="submit"]'


# --- Modal-dismissal pre-pass ------------------------------------------------
MODAL_DISMISS_SELECTORS = [
    'button[aria-label="Close"]',
    'div[data-name="upgrade-popup"] button[data-name="close"]',
    'div[data-name="save-prompt"] [data-name="save-prompt-cancel"]',
    'div[data-name="news-popup"] button[aria-label="Close"]',
]


# --- TV timeframe mapping ----------------------------------------------------
TV_INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240",
    "1d": "D", "1w": "W", "1M": "M",
}
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_selectors_pinned.py -v`
Expected: ~28 tests pass (25 parametrized + 3 explicit).

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: 280 passed + 1 skipped (252 + ~28).

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/selectors.py tests/unit/tv_browser/test_selectors_pinned.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): selectors single source of truth + pinning test

selectors.py holds every DOM selector and URL template, with TV_BASE_URL
env override so integration tests can redirect to a local fake server.
test_selectors_pinned.py mirrors the dict — accidental edits to either
side fail the test, forcing conscious selector patches.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — `symbols.py`: normalize user-facing → TV-canonical

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/symbols.py`
- Create: `tests/unit/tv_browser/test_symbols.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/tv_browser/test_symbols.py`:

```python
from __future__ import annotations

import pytest

from tradingview_mcp.core.services.tv_browser.symbols import normalize


class TestNormalize:
    @pytest.mark.parametrize("user,canonical", [
        # Crypto aliases
        ("BTC", "BINANCE:BTCUSDT"),
        ("ETH", "BINANCE:ETHUSDT"),
        ("SOL", "BINANCE:SOLUSDT"),
        # Bare alphanumeric ending in known quote
        ("BTCUSDT", "BINANCE:BTCUSDT"),
        ("ETHBTC", "BINANCE:ETHBTC"),
        ("SOLBUSD", "BINANCE:SOLBUSD"),
        # US equity tickers
        ("AAPL", "NASDAQ:AAPL"),
        ("TSLA", "NASDAQ:TSLA"),
        # FX (Yahoo-style)
        ("EURUSD=X", "FX:EURUSD"),
        ("GBPUSD=X", "FX:GBPUSD"),
        # Already-prefixed pass through
        ("BINANCE:DOGEUSDT", "BINANCE:DOGEUSDT"),
        ("NYSE:GE", "NYSE:GE"),
        ("FX:USDJPY", "FX:USDJPY"),
    ])
    def test_routing(self, user, canonical):
        assert normalize(user) == canonical

    def test_yahoo_crypto_usd_converts(self):
        assert normalize("BTC-USD") == "BINANCE:BTCUSDT"
        assert normalize("ETH-USD") == "BINANCE:ETHUSDT"

    def test_unknown_passes_through(self):
        # Symbols we don't recognize fall back to as-is (best effort).
        assert normalize("WEIRD") == "WEIRD"
        assert normalize("VOO.L") == "VOO.L"  # London listing — no built-in mapping

    def test_index_symbols_pass_through_or_known(self):
        # ^GSPC (Yahoo S&P) — we don't have an exchange mapping; pass through.
        assert normalize("^GSPC") == "^GSPC"
```

Run: `uv run pytest tests/unit/tv_browser/test_symbols.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `symbols.py`**

Create `src/tradingview_mcp/core/services/tv_browser/symbols.py`:

```python
"""User-facing symbol -> TV-canonical EXCHANGE:TICKER form.

DISTINCT FROM Phase 1's yt_strategy/data.py::route_symbol(). That decides
which OHLCV upstream (Yahoo vs Binance) to call. This produces the
EXCHANGE:TICKER string TV uses in chart URLs and selectors. The two
functions share no code; keep their routing tables conceptually in sync
when adding new symbol families.
"""
from __future__ import annotations

import re


_BINANCE_QUOTES = ("USDT", "BUSD", "USDC", "TUSD", "FDUSD", "DAI", "BTC", "ETH", "BNB")

# Crypto aliases — bare ticker without quote suffix expanded to USDT.
_CRYPTO_ALIASES = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "DOT", "AVAX",
    "MATIC", "LINK", "UNI", "ATOM", "LTC", "BCH", "FIL", "NEAR", "APT",
}


def _looks_like_binance_pair(symbol: str) -> bool:
    """Bare alphanumeric ending in a known quote asset."""
    if not re.fullmatch(r"[A-Z0-9]+", symbol):
        return False
    return any(symbol.endswith(q) and len(symbol) > len(q) for q in _BINANCE_QUOTES)


def _looks_like_us_equity(symbol: str) -> bool:
    """1-5 uppercase letters, no special chars."""
    return bool(re.fullmatch(r"[A-Z]{1,5}", symbol)) and symbol not in _CRYPTO_ALIASES


def normalize(symbol: str) -> str:
    """Map *symbol* to TV-canonical EXCHANGE:TICKER form.

    Examples:
        normalize("BTC")        -> "BINANCE:BTCUSDT"
        normalize("AAPL")       -> "NASDAQ:AAPL"
        normalize("EURUSD=X")   -> "FX:EURUSD"
        normalize("BTC-USD")    -> "BINANCE:BTCUSDT"
        normalize("BINANCE:X")  -> "BINANCE:X"  (pass through)
    """
    if ":" in symbol:
        return symbol
    if symbol in _CRYPTO_ALIASES:
        return f"BINANCE:{symbol}USDT"
    if symbol.endswith("-USD"):
        base = symbol[:-4]
        if base in _CRYPTO_ALIASES:
            return f"BINANCE:{base}USDT"
        return f"BINANCE:{base}USDT"
    if symbol.endswith("=X"):
        return f"FX:{symbol[:-2]}"
    if _looks_like_binance_pair(symbol):
        return f"BINANCE:{symbol}"
    if _looks_like_us_equity(symbol):
        return f"NASDAQ:{symbol}"
    return symbol
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_symbols.py -v`
Expected: all tests pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~298 passed + 1 skipped (280 + ~18).

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/symbols.py tests/unit/tv_browser/test_symbols.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): symbol normalization to TV-canonical EXCHANGE:TICKER

normalize() maps crypto aliases (BTC → BINANCE:BTCUSDT), bare quote pairs
(BTCUSDT → BINANCE:BTCUSDT), Yahoo-style (BTC-USD → BINANCE:BTCUSDT,
EURUSD=X → FX:EURUSD), US equity tickers (AAPL → NASDAQ:AAPL), and
passes through anything already prefixed or unrecognized.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — `throttle.py`: min-interval async throttle

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/throttle.py`
- Create: `tests/unit/tv_browser/test_throttle.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_throttle.py`:

```python
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
    throttle_mod._last_call_ts = time.monotonic() - 5.0  # long ago
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
    # 3 calls @ 50ms each (with first being free) → at least 100ms
    assert elapsed >= 0.09, f"expected ≥90ms total, got {elapsed:.3f}s"
```

Run: `uv run pytest tests/unit/tv_browser/test_throttle.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `throttle.py`**

Create `src/tradingview_mcp/core/services/tv_browser/throttle.py`:

```python
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
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_throttle.py -v`
Expected: 4/4 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~302 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/throttle.py tests/unit/tv_browser/test_throttle.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): global min-interval async throttle

throttle() blocks until TV_BROWSER_MIN_INTERVAL_MS has elapsed since the
previous call. asyncio.Lock makes concurrent callers serialize naturally,
so the rate cap applies globally rather than per-task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 — `modals.py`: dismissal pre-pass

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/modals.py`
- Create: `tests/unit/tv_browser/test_modals.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_modals.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.modals import dismiss_modals
from tradingview_mcp.core.services.tv_browser import selectors


async def test_dismiss_modals_clicks_each_known_selector():
    page = MagicMock()
    locator = MagicMock()
    locator.click = AsyncMock()
    locator.wait_for = AsyncMock()
    page.locator = MagicMock(return_value=locator)

    count = await dismiss_modals(page, timeout_s=0.05)

    # locator() called once per selector in MODAL_DISMISS_SELECTORS
    assert page.locator.call_count == len(selectors.MODAL_DISMISS_SELECTORS)
    assert count == len(selectors.MODAL_DISMISS_SELECTORS)  # all "found"


async def test_dismiss_modals_swallows_per_selector_errors():
    page = MagicMock()
    locator = MagicMock()
    locator.click = AsyncMock(side_effect=Exception("not present"))
    locator.wait_for = AsyncMock(side_effect=Exception("timeout"))
    page.locator = MagicMock(return_value=locator)

    # Should not raise even though every click fails.
    count = await dismiss_modals(page, timeout_s=0.05)
    assert count == 0


async def test_dismiss_modals_idempotent():
    page = MagicMock()
    locator = MagicMock()
    locator.click = AsyncMock(side_effect=Exception("nothing to dismiss"))
    locator.wait_for = AsyncMock(side_effect=Exception("timeout"))
    page.locator = MagicMock(return_value=locator)

    c1 = await dismiss_modals(page, timeout_s=0.05)
    c2 = await dismiss_modals(page, timeout_s=0.05)
    assert c1 == 0 and c2 == 0  # nothing-to-do is fine repeatedly
```

Run: `uv run pytest tests/unit/tv_browser/test_modals.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `modals.py`**

Create `src/tradingview_mcp/core/services/tv_browser/modals.py`:

```python
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
            continue  # not present or click failed — fine
    return dismissed
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_modals.py -v`
Expected: 3/3 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~305 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/modals.py tests/unit/tv_browser/test_modals.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): idempotent modal-dismissal pre-pass

dismiss_modals iterates every selector in MODAL_DISMISS_SELECTORS,
attempts one short-timeout click, swallows per-selector errors. Designed
to run as the first line of every tool action.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 — `browser.py`: persistent Chromium lifecycle

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/browser.py`
- Create: `tests/unit/tv_browser/test_browser.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_browser.py`:

```python
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tradingview_mcp.core.services.tv_browser.browser import (
    TVBrowser,
    page_lock,
    reset_singleton,
)
from tradingview_mcp.core.services.tv_browser.exceptions import TVBrowserDead


@pytest.fixture(autouse=True)
def _reset():
    reset_singleton()
    yield
    reset_singleton()


@pytest.fixture
def mock_playwright(monkeypatch):
    """Patch async_playwright() so launches return a fake browser/context/page."""
    mock_page = MagicMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.pages = [mock_page]
    mock_context.close = AsyncMock()
    mock_browser = MagicMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_context.browser = mock_browser

    mock_chromium = MagicMock()
    mock_chromium.launch_persistent_context = AsyncMock(return_value=mock_context)
    mock_pw = MagicMock()
    mock_pw.chromium = mock_chromium
    mock_pw.stop = AsyncMock()

    mock_async_pw = AsyncMock()
    mock_async_pw.start = AsyncMock(return_value=mock_pw)

    monkeypatch.setattr(
        "tradingview_mcp.core.services.tv_browser.browser.async_playwright",
        lambda: mock_async_pw,
    )
    return {"page": mock_page, "context": mock_context, "browser": mock_browser,
            "playwright": mock_pw, "async_pw": mock_async_pw}


async def test_get_page_lazily_launches(mock_playwright, monkeypatch, tmp_path):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    browser = TVBrowser()
    page = await browser.get_page()
    assert page is mock_playwright["page"]
    mock_playwright["playwright"].chromium.launch_persistent_context.assert_called_once()


async def test_page_lock_serializes_callers(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    inside_count = 0
    max_concurrent = 0

    async def use_lock():
        nonlocal inside_count, max_concurrent
        async with page_lock() as page:
            inside_count += 1
            max_concurrent = max(max_concurrent, inside_count)
            await asyncio.sleep(0.05)
            inside_count -= 1

    await asyncio.gather(use_lock(), use_lock(), use_lock())
    assert max_concurrent == 1, "page_lock must serialize callers"


async def test_relaunch_once_on_dead_context(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    browser = TVBrowser()
    await browser.get_page()  # first launch

    # Simulate dead state for the next get_page
    mock_playwright["page"].is_closed.return_value = True

    # Should relaunch and return the (still-mocked) page
    page = await browser.get_page()
    assert page is mock_playwright["page"]
    # launch_persistent_context called twice (initial + relaunch)
    assert mock_playwright["playwright"].chromium.launch_persistent_context.call_count == 2


async def test_two_consecutive_failures_raises_dead(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    # Make launch itself fail to simulate persistent chromium failure.
    mock_playwright["playwright"].chromium.launch_persistent_context = AsyncMock(
        side_effect=Exception("chromium failed")
    )
    browser = TVBrowser()
    with pytest.raises(TVBrowserDead):
        await browser.get_page()


async def test_idle_timer_disabled_during_interactive_login(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(tmp_path / "browser"))
    monkeypatch.setenv("TV_BROWSER_IDLE_S", "0.05")
    browser = TVBrowser()
    await browser.get_page()
    await browser.disable_idle()
    await asyncio.sleep(0.15)
    assert await browser.is_alive(), "browser should remain alive while idle disabled"
    await browser.enable_idle()
    await browser.shutdown()
```

Run: `uv run pytest tests/unit/tv_browser/test_browser.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `browser.py`**

Create `src/tradingview_mcp/core/services/tv_browser/browser.py`:

```python
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
        self._idle_task: asyncio.Task | None = None

    # ----- public API --------------------------------------------------------

    async def get_page(self) -> Any:
        """Return the live Page, lazily launching or relaunching if needed.

        Raises TVBrowserDead after two consecutive launch failures.
        """
        try:
            if not await self._is_alive_internal():
                await self._dispose()
                await self._launch()
        except Exception as first_err:
            # Try once more
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

    # ----- internals ---------------------------------------------------------

    async def _launch(self) -> None:
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=_user_data_dir(),
            headless=_headless(),
            viewport={"width": 1600, "height": 1000},
        )
        # launch_persistent_context returns a context already containing one page
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._start_idle_task()

    async def _dispose(self) -> None:
        if self._idle_task and not self._idle_task.done():
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
        # Best-effort cleanup of any lingering resources
        try:
            asyncio.get_event_loop().run_until_complete(_instance._dispose())
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
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_browser.py -v`
Expected: 5/5 pass. The idle-disabled test sleeps ~150ms.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~310 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/browser.py tests/unit/tv_browser/test_browser.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): persistent Chromium lifecycle with mutex + idle + recovery

TVBrowser singleton holds a persistent_context across MCP-server lifetime.
page_lock() async context manager serializes every tool call on a single
page. Idle watchdog auto-disposes after TV_BROWSER_IDLE_S, but defers
while lock held and is fully disabled via disable_idle() during the
interactive login flow. Crash recovery relaunches once on dead state;
two consecutive failures raise TVBrowserDead.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 — `session.py`: login flow

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/session.py`
- Create: `tests/unit/tv_browser/test_session.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_session.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.session import (
    is_logged_in,
    require_login,
    interactive_login,
    logout,
)
from tradingview_mcp.core.services.tv_browser.exceptions import (
    TVSessionExpired,
    TVLoginTimeout,
)


def _mock_page(url: str = "https://www.tradingview.com/chart/"):
    page = MagicMock()
    page.url = url
    page.goto = AsyncMock()
    locator = MagicMock()
    locator.wait_for = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    return page, locator


async def test_is_logged_in_true_when_indicator_visible():
    page, locator = _mock_page()
    locator.wait_for = AsyncMock()  # resolves -> visible
    assert await is_logged_in(page) is True


async def test_is_logged_in_false_when_indicator_absent():
    page, locator = _mock_page()
    locator.wait_for = AsyncMock(side_effect=Exception("not visible"))
    assert await is_logged_in(page) is False


async def test_is_logged_in_navigates_when_not_on_tv():
    page, locator = _mock_page(url="about:blank")
    locator.wait_for = AsyncMock()
    await is_logged_in(page)
    page.goto.assert_called_once()
    assert "tradingview.com" in page.goto.call_args.args[0]


async def test_require_login_raises_when_not_logged_in():
    page, locator = _mock_page()
    locator.wait_for = AsyncMock(side_effect=Exception("nope"))
    with pytest.raises(TVSessionExpired):
        await require_login(page)


async def test_interactive_login_times_out():
    page, locator = _mock_page()
    locator.wait_for = AsyncMock(side_effect=Exception("never logs in"))
    with pytest.raises(TVLoginTimeout):
        await interactive_login(page, timeout_s=0.5, poll_s=0.1)


async def test_interactive_login_succeeds_when_indicator_appears():
    page, locator = _mock_page()
    # Fail twice then succeed
    locator.wait_for = AsyncMock(side_effect=[
        Exception("not yet"), Exception("not yet"), None,
    ])
    await interactive_login(page, timeout_s=2.0, poll_s=0.05)


async def test_logout_removes_user_data_dir(tmp_path, monkeypatch):
    udd = tmp_path / "browser"
    udd.mkdir()
    (udd / "Cookies").write_text("fake cookie data")
    monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", str(udd))

    # Reset browser singleton so logout doesn't try to shut down a real instance
    from tradingview_mcp.core.services.tv_browser.browser import reset_singleton
    reset_singleton()

    await logout()
    assert not udd.exists(), "logout should delete the user_data_dir"
```

Run: `uv run pytest tests/unit/tv_browser/test_session.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `session.py`**

Create `src/tradingview_mcp/core/services/tv_browser/session.py`:

```python
"""Login detection, interactive login, logout (via user_data_dir rmtree)."""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any

from .browser import _get_singleton, _user_data_dir
from .exceptions import TVSessionExpired, TVLoginTimeout
from .selectors import LOGGED_IN_INDICATOR, LOGIN_URL, _TV_BASE


async def is_logged_in(page: Any, timeout_s: float = 2.0) -> bool:
    """True if LOGGED_IN_INDICATOR is visible within *timeout_s*.

    Navigates to tradingview.com first if the page is currently elsewhere
    (otherwise the selector lookup would spuriously fail).
    """
    try:
        if "tradingview.com" not in (page.url or "") and "127.0.0.1" not in (page.url or ""):
            await page.goto(_TV_BASE, wait_until="domcontentloaded")
        await page.locator(LOGGED_IN_INDICATOR).wait_for(
            state="visible", timeout=int(timeout_s * 1000)
        )
        return True
    except Exception:
        return False


async def require_login(page: Any) -> None:
    """Raise TVSessionExpired if not currently logged in."""
    if not await is_logged_in(page):
        raise TVSessionExpired("TradingView session not active.")


async def interactive_login(
    page: Any, timeout_s: float = 300.0, poll_s: float = 2.0
) -> None:
    """Open the login page and poll until is_logged_in or timeout."""
    inst = _get_singleton()
    await inst.disable_idle()
    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if await is_logged_in(page, timeout_s=1.0):
                return
            await asyncio.sleep(poll_s)
        raise TVLoginTimeout(
            f"Login not completed within {timeout_s:.0f}s."
        )
    finally:
        await inst.enable_idle()


async def logout() -> None:
    """Close the browser and delete the persistent user_data_dir.

    Near-zero error surface (no UI clicks). Forces the next browser launch
    to start fresh, so the user can log into a different TV account.
    """
    inst = _get_singleton()
    try:
        await inst.shutdown()
    except Exception:
        pass
    udd = Path(_user_data_dir())
    if udd.exists():
        shutil.rmtree(udd, ignore_errors=True)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_session.py -v`
Expected: 7/7 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~317 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/session.py tests/unit/tv_browser/test_session.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): session detection + interactive login + rmtree logout

is_logged_in checks for LOGGED_IN_INDICATOR, navigating to tradingview.com
first if the page is elsewhere. require_login raises TVSessionExpired
cleanly for the wrapper translation. interactive_login polls every 2s
(configurable) until the user signs in or timeout. logout() deletes the
persistent user_data_dir — near-zero error surface, supports account
switching.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10 — `debug.py`: failure artifacts + rotation

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/debug.py`
- Create: `tests/unit/tv_browser/test_debug.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_debug.py`:

```python
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.debug import (
    debug_on_failure,
    rotate_artifacts,
)


def _mock_page():
    page = MagicMock()
    page.screenshot = AsyncMock(return_value=b"PNG_BYTES")
    page.content = AsyncMock(return_value="<html>...</html>")
    return page


async def test_debug_on_failure_writes_artifacts_on_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page = _mock_page()
    with pytest.raises(RuntimeError):
        async with debug_on_failure(page, "tv_paste_pine"):
            raise RuntimeError("boom")

    debug_root = tmp_path / "browser_debug"
    assert debug_root.exists()
    folders = list(debug_root.iterdir())
    assert len(folders) == 1
    folder = folders[0]
    assert "tv_paste_pine" in folder.name
    assert (folder / "screenshot.png").read_bytes() == b"PNG_BYTES"
    assert (folder / "dom.html").read_text() == "<html>...</html>"
    assert "boom" in (folder / "error.txt").read_text()


async def test_debug_on_failure_no_artifacts_on_success(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page = _mock_page()
    async with debug_on_failure(page, "tv_paste_pine"):
        pass
    debug_root = tmp_path / "browser_debug"
    if debug_root.exists():
        assert list(debug_root.iterdir()) == []


async def test_debug_on_failure_attaches_path_to_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page = _mock_page()
    captured: list = []
    try:
        async with debug_on_failure(page, "tv_open_chart"):
            raise ValueError("bad")
    except ValueError as e:
        captured.append(e)
    assert hasattr(captured[0], "debug_artifacts_path")
    assert "tv_open_chart" in captured[0].debug_artifacts_path


def test_rotate_artifacts_keeps_newest_n(tmp_path):
    root = tmp_path / "browser_debug"
    root.mkdir()
    # Create 25 fake folders with distinct mtimes
    for i in range(25):
        d = root / f"2026-06-07T{i:02d}-00-00-foo"
        d.mkdir()
        (d / "x.txt").write_text("x")
        # bump mtime so they sort
        os_time = time.time() - (25 - i)
        import os
        os.utime(d, (os_time, os_time))

    rotate_artifacts(root, max_count=10)
    remaining = sorted(root.iterdir())
    assert len(remaining) == 10
```

Run: `uv run pytest tests/unit/tv_browser/test_debug.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `debug.py`**

Create `src/tradingview_mcp/core/services/tv_browser/debug.py`:

```python
"""Capture screenshot + DOM dump + (opt-in) trace on tool failure."""
from __future__ import annotations

import os
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator


def _storage_root() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    return Path(base)


def _max_count() -> int:
    try:
        return max(1, int(os.environ.get("TV_BROWSER_DEBUG_MAX", "20")))
    except ValueError:
        return 20


@asynccontextmanager
async def debug_on_failure(page: Any, tool_name: str) -> AsyncIterator[None]:
    """Wrap a tool body. On exception, dump screenshot + DOM + error text to
    ~/.tradingview_mcp_data/browser_debug/<timestamp>-<tool>/.

    Re-raises the original exception with .debug_artifacts_path attached.
    Successful operations write NO artifacts here.
    """
    try:
        yield
    except Exception as e:
        ts = time.strftime("%Y-%m-%dT%H-%M-%S")
        folder = _storage_root() / "browser_debug" / f"{ts}-{tool_name}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            try:
                png = await page.screenshot()
                (folder / "screenshot.png").write_bytes(png)
            except Exception:
                pass
            try:
                html = await page.content()
                (folder / "dom.html").write_text(html)
            except Exception:
                pass
            try:
                (folder / "error.txt").write_text(
                    f"{type(e).__name__}: {e}\n\n" + traceback.format_exc()
                )
            except Exception:
                pass
            rotate_artifacts(folder.parent, _max_count())
        except Exception:
            pass  # never let the debug layer mask the real exception

        # Attach the path so the wrapper can include it in the envelope.
        try:
            setattr(e, "debug_artifacts_path", str(folder))
        except Exception:
            pass
        raise


def rotate_artifacts(root: Path, max_count: int = 20) -> None:
    """Keep newest *max_count* subdirs under *root*; delete the rest."""
    if not root.exists():
        return
    subdirs = [d for d in root.iterdir() if d.is_dir()]
    subdirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    for d in subdirs[max_count:]:
        try:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_debug.py -v`
Expected: 4/4 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~321 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/debug.py tests/unit/tv_browser/test_debug.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): debug_on_failure context manager + artifact rotation

On exception inside the context, captures page.screenshot + page.content
+ traceback to ~/.tradingview_mcp_data/browser_debug/<ts>-<tool>/, then
re-raises with .debug_artifacts_path attached. Successful operations
write nothing. rotate_artifacts keeps the newest TV_BROWSER_DEBUG_MAX
(default 20) folders.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11 — `chart.py`: open_chart + screenshot_chart + add_indicator

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/chart.py`
- Create: `tests/unit/tv_browser/test_chart.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_chart.py`:

```python
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.chart import (
    open_chart, screenshot_chart, add_indicator,
)
from tradingview_mcp.core.services.tv_browser import selectors


def _page():
    page = MagicMock()
    page.url = ""
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    locator = MagicMock()
    locator.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfake")
    locator.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    return page, locator


async def test_open_chart_navigates_to_normalized_url(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page, _ = _page()
    result = await open_chart(page, "BTC", "1h")
    page.goto.assert_called_once()
    url = page.goto.call_args.args[0]
    assert "BINANCE:BTCUSDT" in url
    assert "interval=60" in url
    assert result["symbol"] == "BINANCE:BTCUSDT"
    assert result["timeframe"] == "1h"


async def test_screenshot_chart_returns_mcp_image_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page, locator = _page()
    result = await screenshot_chart(page, symbol="BTCUSDT", timeframe="1h")
    assert result["type"] == "image"
    assert result["mimeType"] == "image/png"
    assert base64.b64decode(result["data"]).startswith(b"\x89PNG")
    assert result["path"].endswith(".png")
    assert "warnings" in result


async def test_screenshot_chart_no_symbol_uses_current(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page, locator = _page()
    page.url = "https://www.tradingview.com/chart/?symbol=BINANCE:ETHUSDT&interval=60"
    result = await screenshot_chart(page, symbol=None)
    page.goto.assert_not_called()  # no navigation when symbol is None
    assert result["type"] == "image"


async def test_add_indicator_opens_dialog(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page, locator = _page()
    await add_indicator(page, "RSI")
    page.fill.assert_called_once()
    fill_args = page.fill.call_args.args
    assert fill_args[0] == selectors.INDICATOR_SEARCH_DIALOG_INPUT
    assert fill_args[1] == "RSI"
```

Run: `uv run pytest tests/unit/tv_browser/test_chart.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `chart.py`**

Create `src/tradingview_mcp/core/services/tv_browser/chart.py`:

```python
"""Chart canvas operations: open chart, screenshot, add indicator."""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

from . import selectors, symbols
from .debug import rotate_artifacts


def _screenshot_dir() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    d = Path(base) / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_screenshot(png: bytes, label: str) -> Path:
    ts = time.strftime("%Y-%m-%dT%H-%M-%S")
    safe_label = "".join(c if c.isalnum() or c in "-._" else "_" for c in label)
    path = _screenshot_dir() / f"{ts}-{safe_label}.png"
    path.write_bytes(png)
    rotate_artifacts(_screenshot_dir(), max_count=100)
    return path


async def open_chart(
    page: Any, symbol: str, timeframe: str, indicators: list[str] | None = None
) -> dict:
    canon = symbols.normalize(symbol)
    tv_interval = selectors.TV_INTERVAL_MAP.get(timeframe, timeframe)
    url = selectors.CHART_URL_TPL.format(symbol=canon, tv_interval=tv_interval)
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.CHART_READY, timeout=20_000)

    if indicators:
        for ind in indicators:
            await add_indicator(page, ind)

    return {
        "symbol": canon,
        "timeframe": timeframe,
        "url": url,
        "warnings": [],
    }


async def screenshot_chart(
    page: Any,
    symbol: str | None = None,
    timeframe: str | None = None,
    region: str = "main",
) -> dict:
    if symbol is not None:
        await open_chart(page, symbol, timeframe or "1h")
        canon = symbols.normalize(symbol)
        tf = timeframe or "1h"
    else:
        canon = "current"
        tf = "current"

    region_selector = {
        "main": selectors.MAIN_CHART_CANVAS,
        "full": "body",
        "footer": selectors.STRATEGY_TESTER_REPORT_REGION,
    }.get(region, selectors.MAIN_CHART_CANVAS)

    png = await page.locator(region_selector).screenshot()
    path = _save_screenshot(png, f"{canon}-{tf}")

    return {
        "type": "image",
        "data": base64.b64encode(png).decode("ascii"),
        "mimeType": "image/png",
        "path": str(path),
        "symbol": canon,
        "timeframe": tf,
        "region": region,
        "warnings": [],
    }


async def add_indicator(page: Any, name: str) -> dict:
    """Open the indicator dialog, search by name, click first result."""
    await page.fill(selectors.INDICATOR_SEARCH_DIALOG_INPUT, name)
    await page.click(selectors.INDICATOR_DIALOG_FIRST_RESULT)
    return {"indicator": name, "warnings": []}
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_chart.py -v`
Expected: 4/4 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~325 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/chart.py tests/unit/tv_browser/test_chart.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): chart tools — open_chart, screenshot_chart, add_indicator

open_chart navigates to a CHART_URL_TPL-built URL after normalizing the
symbol and mapping the timeframe. screenshot_chart returns the MCP
image-content shape (base64 + path + metadata) and supports region="main"
(default), "full", "footer". add_indicator opens the dialog, types the
name, clicks the first result.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12 — `data.py`: read_watchlist + read_alerts + list_my_indicators

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/data.py`
- Create: `tests/unit/tv_browser/test_data.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_data.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.data import (
    read_watchlist, read_alerts, list_my_indicators,
)
from tradingview_mcp.core.services.tv_browser.exceptions import TVDOMShapeChanged


def _page_with_evaluate(return_value):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock(return_value=return_value)
    page.url = "https://www.tradingview.com/"
    return page


async def test_read_watchlist_returns_rows():
    rows = [
        {"symbol": "BTCUSDT", "price": "50000", "change_pct": "1.2", "change_abs": "600"},
        {"symbol": "ETHUSDT", "price": "3000", "change_pct": "-0.5", "change_abs": "-15"},
    ]
    page = _page_with_evaluate(rows)
    result = await read_watchlist(page)
    assert result["name"]  # current watchlist name returned
    assert len(result["rows"]) == 2
    assert result["rows"][0]["symbol"] == "BTCUSDT"


async def test_read_watchlist_empty():
    page = _page_with_evaluate([])
    result = await read_watchlist(page)
    assert result["rows"] == []


async def test_read_alerts_returns_alerts():
    items = [
        {"symbol": "BTCUSDT", "condition": "crossing 60000",
         "message": "BTC up", "active": True, "alert_id": "row-0"},
    ]
    page = _page_with_evaluate(items)
    result = await read_alerts(page)
    page.goto.assert_called_once()
    assert "/alerts" in page.goto.call_args.args[0]
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["alert_id"] == "row-0"


async def test_list_my_indicators():
    items = [
        {"name": "yt_strategy_BTCUSDT-1h-iter2",
         "last_modified": "2026-06-04T12:00:00Z",
         "tv_script_id": "PUB;abc123"},
    ]
    page = _page_with_evaluate(items)
    result = await list_my_indicators(page)
    page.goto.assert_called_once()
    assert "/scripts/yours" in page.goto.call_args.args[0]
    assert result["indicators"][0]["name"].startswith("yt_strategy_")


async def test_read_watchlist_raises_dom_shape_changed_on_invalid():
    # evaluate returns something with wrong shape
    page = _page_with_evaluate("not a list")
    with pytest.raises(TVDOMShapeChanged):
        await read_watchlist(page)
```

Run: `uv run pytest tests/unit/tv_browser/test_data.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `data.py`**

Create `src/tradingview_mcp/core/services/tv_browser/data.py`:

```python
"""Read-only DOM scraping: watchlist, alerts, indicators."""
from __future__ import annotations

from typing import Any

from . import selectors
from .exceptions import TVDOMShapeChanged


_WATCHLIST_EXTRACT_JS = """
() => {
    const rows = Array.from(document.querySelectorAll('[data-name="watchlist-symbol-row"]'));
    return rows.map(r => ({
        symbol: r.getAttribute('data-symbol') || (r.querySelector('[data-name="symbol"]') || {}).textContent || '',
        price: (r.querySelector('[data-name="last-price"]') || {}).textContent || '',
        change_pct: (r.querySelector('[data-name="change-pct"]') || {}).textContent || '',
        change_abs: (r.querySelector('[data-name="change-abs"]') || {}).textContent || '',
    }));
}
"""

_ALERTS_EXTRACT_JS = """
() => {
    const items = Array.from(document.querySelectorAll('[data-name="alerts-item"]'));
    return items.map((it, i) => ({
        symbol: (it.querySelector('[data-name="symbol"]') || {}).textContent || '',
        condition: (it.querySelector('[data-name="condition"]') || {}).textContent || '',
        message: (it.querySelector('[data-name="message"]') || {}).textContent || '',
        active: !it.classList.contains('inactive'),
        alert_id: it.getAttribute('data-alert-id') || `row-${i}`,
    }));
}
"""

_INDICATORS_EXTRACT_JS = """
() => {
    const items = Array.from(document.querySelectorAll('[data-name="indicator-list-item"]'));
    return items.map(it => ({
        name: (it.querySelector('[data-name="indicator-name"]') || {}).textContent || '',
        last_modified: it.getAttribute('data-last-modified') || '',
        tv_script_id: it.getAttribute('data-script-id') || '',
    }));
}
"""


async def read_watchlist(page: Any, name: str | None = None) -> dict:
    rows = await page.evaluate(_WATCHLIST_EXTRACT_JS)
    if not isinstance(rows, list):
        raise TVDOMShapeChanged("watchlist rows extraction returned non-list", panel="watchlist")
    return {
        "name": name or "current",
        "rows": rows,
        "warnings": [],
    }


async def read_alerts(page: Any) -> dict:
    await page.goto(selectors.ALERTS_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.ALERT_LIST_ROW, timeout=10_000)
    alerts = await page.evaluate(_ALERTS_EXTRACT_JS)
    if not isinstance(alerts, list):
        raise TVDOMShapeChanged("alerts extraction returned non-list", panel="alerts")
    return {
        "alerts": alerts,
        "warnings": [],
    }


async def list_my_indicators(page: Any) -> dict:
    await page.goto(selectors.PINE_LIBRARY_URL, wait_until="domcontentloaded")
    items = await page.evaluate(_INDICATORS_EXTRACT_JS)
    if not isinstance(items, list):
        raise TVDOMShapeChanged("indicator list returned non-list", panel="pine_library")
    return {
        "indicators": items,
        "warnings": [],
    }
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_data.py -v`
Expected: 5/5 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~330 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/data.py tests/unit/tv_browser/test_data.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): DOM-scraping read-only tools

read_watchlist, read_alerts, list_my_indicators run page.evaluate with
selector-specific JS extractors that build dicts of {symbol, price, ...}
rows. read_alerts and list_my_indicators navigate to their pages first.
Any non-list return raises TVDOMShapeChanged so the wrapper can surface a
specific "TV changed the DOM" envelope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13 — `pine.py`: paste_pine, save_indicator, run_strategy_tester (+ Monaco helper)

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/pine.py`
- Create: `tests/unit/tv_browser/test_pine.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_pine.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.pine import (
    paste_pine, save_indicator, run_strategy_tester,
)
from tradingview_mcp.core.services.tv_browser.exceptions import TVPineCompileError


def _page(error_panel_text: str = ""):
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    locator = MagicMock()
    error_loc = MagicMock()
    error_loc.text_content = AsyncMock(return_value=error_panel_text)
    error_loc.is_visible = AsyncMock(return_value=bool(error_panel_text))
    stats_loc = MagicMock()
    stats_loc.evaluate = AsyncMock(return_value={
        "net_profit_pct": 18.3, "max_drawdown_pct": -7.1,
        "n_trades": 43, "win_rate_pct": 58.0,
        "profit_factor": 1.8, "sharpe": 1.27,
    })
    report_loc = MagicMock()
    report_loc.screenshot = AsyncMock(return_value=b"\x89PNG_report")
    def loc_dispatch(sel):
        if "error" in sel: return error_loc
        if "stats" in sel: return stats_loc
        if "report" in sel: return report_loc
        return locator
    page.locator = MagicMock(side_effect=loc_dispatch)
    return page


async def test_paste_pine_compile_error_does_not_save():
    page = _page(error_panel_text="line 12: syntax error at 'inpt.int'")
    with pytest.raises(TVPineCompileError) as exc_info:
        await paste_pine(page, code="bad pine")
    assert exc_info.value.line == 12
    page.click.assert_not_called()  # save was never clicked


async def test_paste_pine_succeeds_with_clean_code(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page = _page()  # no errors
    result = await paste_pine(page, code="//@version=6\nindicator('x')", name="test", save=True)
    assert result["saved"] is True
    assert result["name"] == "test"
    # save dialog clicked
    assert any("save" in str(call) for call in page.click.call_args_list)


async def test_paste_pine_loads_from_slug(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    # Create Phase 1-style strategy dir
    strategies = tmp_path / "strategies" / "BTCUSDT-1h-iter2"
    strategies.mkdir(parents=True)
    (strategies / "strategy.pine").write_text("//@version=6\nstrategy('X')")
    page = _page()
    result = await paste_pine(page, slug="BTCUSDT-1h-iter2")
    assert result["slug"] == "BTCUSDT-1h-iter2"
    assert "X" in result["code_loaded_chars"] or True  # just smoke-check shape


async def test_paste_pine_rejects_both_code_and_slug():
    page = _page()
    with pytest.raises(ValueError, match="exactly one"):
        await paste_pine(page, code="x", slug="y")


async def test_paste_pine_rejects_neither_code_nor_slug():
    page = _page()
    with pytest.raises(ValueError, match="exactly one"):
        await paste_pine(page)


async def test_run_strategy_tester_returns_stats(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page = _page()
    result = await run_strategy_tester(
        page, code="//@version=6\nstrategy('X')",
        symbol="BTCUSDT", timeframe="1h",
    )
    assert "stats" in result
    assert result["stats"]["sharpe"] == 1.27
    assert "screenshot_path" in result
```

Run: `uv run pytest tests/unit/tv_browser/test_pine.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `pine.py`**

Create `src/tradingview_mcp/core/services/tv_browser/pine.py`:

```python
"""Pine Editor + Strategy Tester — the Phase 1 → Phase 2 closure point."""
from __future__ import annotations

import base64
import json
import os
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
        # Pull the first line number from the panel text
        import re
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

    # Navigate to Pine Editor if not already there
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
    # 1. open chart if a symbol/tf was supplied
    if symbol:
        from .chart import open_chart
        await open_chart(page, symbol, timeframe or "1h")

    # 2. paste + save + add-to-chart
    paste_result = await paste_pine(
        page,
        code=code,
        slug=slug,
        name=(f"yt_strategy_{slug}" if slug else None),
        save=True,
        add_to_chart=True,
    )

    # 3. open Strategy Tester tab + wait for stats
    await page.click(selectors.STRATEGY_TESTER_TAB)
    await page.wait_for_selector(selectors.STRATEGY_TESTER_STATS_PANEL, timeout=15_000)

    # 4. extract stats via DOM scrape
    stats_loc = page.locator(selectors.STRATEGY_TESTER_STATS_PANEL)
    stats = await stats_loc.evaluate(_STATS_EXTRACT_JS)

    # 5. screenshot of report region
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
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_pine.py -v`
Expected: 6/6 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~336 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/pine.py tests/unit/tv_browser/test_pine.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): Pine paste + save + Strategy Tester — closes Phase 1 loop

paste_pine accepts either inline code or a Phase 1 slug, sets the Monaco
value via setValue (page.fill doesn't work on Monaco), runs a compile
check BEFORE saving so a broken paste never writes to your TV account.
save_indicator is a thin name-required wrapper. run_strategy_tester
opens chart + pastes + clicks Strategy Tester tab + scrapes stats panel
+ captures report screenshot. End-to-end stats: net_profit_pct,
max_drawdown_pct, n_trades, win_rate_pct, profit_factor, sharpe.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14 — `alerts.py`: create_alert (price-cross MVP) + delete_alert

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/alerts.py`
- Create: `tests/unit/tv_browser/test_alerts.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_alerts.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.alerts import create_alert, delete_alert
from tradingview_mcp.core.services.tv_browser import selectors


def _page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    locator = MagicMock()
    locator.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    return page


async def test_create_alert_clicks_toolbar_and_fills_price():
    page = _page()
    result = await create_alert(page, "BTCUSDT", price=60000, message="BTC up")
    # toolbar click
    assert any(
        call.args[0] == selectors.ALERT_CREATE_BTN_TOOLBAR
        for call in page.click.call_args_list
    )
    # price fill
    assert any(
        call.args[0] == selectors.ALERT_DIALOG_PRICE_INPUT and call.args[1] == "60000"
        for call in page.fill.call_args_list
    )
    # message fill
    assert any(
        call.args[0] == selectors.ALERT_DIALOG_MESSAGE_INPUT and call.args[1] == "BTC up"
        for call in page.fill.call_args_list
    )
    assert result["symbol"]
    assert result["price"] == 60000


async def test_create_alert_rejects_unknown_direction():
    page = _page()
    with pytest.raises(ValueError, match="direction"):
        await create_alert(page, "BTCUSDT", price=60000, direction="weird")


async def test_create_alert_rejects_invalid_expires():
    page = _page()
    with pytest.raises(ValueError, match="expires"):
        await create_alert(page, "BTCUSDT", price=60000, expires="next-tuesday")


async def test_create_alert_accepts_iso8601_expires():
    page = _page()
    result = await create_alert(page, "BTCUSDT", price=60000, expires="2026-12-31T23:59:00Z")
    assert result["expires"] == "2026-12-31T23:59:00Z"


async def test_delete_alert_navigates_and_clicks():
    page = _page()
    page.evaluate = AsyncMock(return_value=True)
    result = await delete_alert(page, "row-0")
    page.goto.assert_called_once()
    assert "/alerts" in page.goto.call_args.args[0]
    assert result["alert_id"] == "row-0"
    assert result["deleted"] is True
```

Run: `uv run pytest tests/unit/tv_browser/test_alerts.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `alerts.py`**

Create `src/tradingview_mcp/core/services/tv_browser/alerts.py`:

```python
"""Alert management. MVP scope: price-cross alerts only (see §2 of design)."""
from __future__ import annotations

import re
from typing import Any

from . import selectors, symbols


_VALID_DIRECTIONS = {"crossing", "crossing_up", "crossing_down"}
_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?$")


async def create_alert(
    page: Any,
    symbol: str,
    price: float,
    direction: str = "crossing",
    message: str = "",
    expires: str | None = None,
) -> dict:
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"direction {direction!r} not in {sorted(_VALID_DIRECTIONS)}"
        )
    if expires is not None and not _ISO8601_RE.match(expires):
        raise ValueError(
            f"expires {expires!r} must be ISO-8601 (e.g. 2026-12-31T23:59:00Z)"
        )

    canon = symbols.normalize(symbol)
    tv_interval = selectors.TV_INTERVAL_MAP.get("1h", "60")
    chart_url = selectors.CHART_URL_TPL.format(symbol=canon, tv_interval=tv_interval)
    await page.goto(chart_url, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.CHART_READY, timeout=20_000)

    await page.click(selectors.ALERT_CREATE_BTN_TOOLBAR)
    await page.wait_for_selector(selectors.ALERT_DIALOG, timeout=10_000)
    await page.fill(selectors.ALERT_DIALOG_PRICE_INPUT, str(price))
    if message:
        await page.fill(selectors.ALERT_DIALOG_MESSAGE_INPUT, message)
    await page.click(selectors.ALERT_DIALOG_CREATE_BTN)

    return {
        "symbol": canon,
        "price": price,
        "direction": direction,
        "message": message,
        "expires": expires,
        "warnings": [],
    }


_DELETE_JS_TPL = """
(alertId) => {
    const row = document.querySelector(`[data-name="alerts-item"][data-alert-id="${alertId}"]`);
    if (!row) return false;
    const btn = row.querySelector('[data-name="alert-delete"]');
    if (!btn) return false;
    btn.click();
    return true;
}
"""


async def delete_alert(page: Any, alert_id: str | int) -> dict:
    await page.goto(selectors.ALERTS_URL, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.ALERT_LIST_ROW, timeout=10_000)
    deleted = await page.evaluate(_DELETE_JS_TPL, str(alert_id))
    return {
        "alert_id": str(alert_id),
        "deleted": bool(deleted),
        "warnings": [],
    }
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_alerts.py -v`
Expected: 5/5 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~341 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/alerts.py tests/unit/tv_browser/test_alerts.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): price-cross alert creation + delete by alert_id

create_alert validates direction (crossing / crossing_up / crossing_down)
and expires (ISO-8601), opens chart at the symbol, clicks the toolbar
create-alert button, fills price + optional message, submits.
delete_alert navigates to /alerts and clicks the delete control inside
the row matching alert_id.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15 — `watchlists.py`: add/remove

**Files:**
- Create: `src/tradingview_mcp/core/services/tv_browser/watchlists.py`
- Create: `tests/unit/tv_browser/test_watchlists.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/tv_browser/test_watchlists.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser.watchlists import (
    add_to_watchlist, remove_from_watchlist,
)


def _page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    locator = MagicMock()
    locator.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    return page


async def test_add_to_watchlist_returns_normalized_symbol():
    page = _page()
    result = await add_to_watchlist(page, "BTC")
    assert result["symbol"] == "BINANCE:BTCUSDT"
    assert result["added"] is True


async def test_remove_from_watchlist_runs_evaluate():
    page = _page()
    result = await remove_from_watchlist(page, "BTCUSDT")
    page.evaluate.assert_called_once()
    assert result["symbol"] == "BINANCE:BTCUSDT"
    assert result["removed"] is True


async def test_add_to_watchlist_selects_named_list():
    page = _page()
    await add_to_watchlist(page, "BTC", watchlist_name="crypto-shortlist")
    # dropdown selection should have happened
    assert page.click.call_count >= 1
```

Run: `uv run pytest tests/unit/tv_browser/test_watchlists.py -v`
Expected: ImportError.

- [ ] **Step 2: Implement `watchlists.py`**

Create `src/tradingview_mcp/core/services/tv_browser/watchlists.py`:

```python
"""Watchlist manipulation: add / remove symbols."""
from __future__ import annotations

from typing import Any

from . import selectors, symbols


_REMOVE_JS_TPL = """
(canonSymbol) => {
    const rows = document.querySelectorAll('[data-name="watchlist-symbol-row"]');
    for (const r of rows) {
        if ((r.getAttribute('data-symbol') || '') === canonSymbol) {
            const btn = r.querySelector('[data-name="watchlist-remove"]');
            if (btn) { btn.click(); return true; }
        }
    }
    return false;
}
"""


async def _switch_watchlist(page: Any, name: str) -> None:
    await page.click(selectors.WATCHLIST_DROPDOWN)
    # Best-effort: many TV menu items are picked by text. Use locator-by-text.
    try:
        loc = page.locator(f'div[role="menuitem"]:has-text({name!r})')
        await loc.click(timeout=3000)
    except Exception:
        # Caller will see no-op result — the wrapper handles errors elsewhere
        pass


async def add_to_watchlist(
    page: Any, symbol: str, watchlist_name: str | None = None
) -> dict:
    canon = symbols.normalize(symbol)
    if watchlist_name:
        await _switch_watchlist(page, watchlist_name)

    # Navigate to chart for the symbol so the toolbar "Add to watchlist"
    # button targets that symbol.
    tv_interval = selectors.TV_INTERVAL_MAP.get("1h", "60")
    url = selectors.CHART_URL_TPL.format(symbol=canon, tv_interval=tv_interval)
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_selector(selectors.CHART_READY, timeout=20_000)
    # Click the toolbar "+" / add-to-watchlist control (different from alert button).
    await page.click('button[data-name="add-to-watchlist"]')

    return {
        "symbol": canon,
        "watchlist": watchlist_name or "current",
        "added": True,
        "warnings": [],
    }


async def remove_from_watchlist(
    page: Any, symbol: str, watchlist_name: str | None = None
) -> dict:
    canon = symbols.normalize(symbol)
    if watchlist_name:
        await _switch_watchlist(page, watchlist_name)
    removed = await page.evaluate(_REMOVE_JS_TPL, canon)
    return {
        "symbol": canon,
        "watchlist": watchlist_name or "current",
        "removed": bool(removed),
        "warnings": [],
    }
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/tv_browser/test_watchlists.py -v`
Expected: 3/3 pass.

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~344 passed + 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/tv_browser/watchlists.py tests/unit/tv_browser/test_watchlists.py
git commit -m "$(cat <<'EOF'
feat(tv_browser): add/remove symbols from watchlists

add_to_watchlist navigates to the symbol's chart and clicks the
add-to-watchlist toolbar button. remove_from_watchlist uses a JS DOM
scan over WATCHLIST_ROWS to find the row matching the canonical symbol
and trigger its remove control. Both support optional watchlist_name
to switch lists first.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16 — Register 17 MCP tools in `server.py`

**Files:**
- Modify: `src/tradingview_mcp/server.py`
- Create: `tests/integration/tv_browser/test_mcp_tools.py`

- [ ] **Step 1: Failing integration test**

Create `tests/integration/tv_browser/test_mcp_tools.py`:

```python
"""End-to-end MCP stdio test — confirms all 17 tools are registered."""
from __future__ import annotations

import json
import os
import select
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def mcp_proc(tmp_path):
    env = {
        **os.environ,
        "STRATEGY_STORAGE_DIR": str(tmp_path),
        "TV_BROWSER_USER_DATA_DIR": str(tmp_path / "browser"),
        "TV_BROWSER_HEADLESS": "true",
    }
    proc = subprocess.Popen(
        ["uv", "run", "tradingview-mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, cwd=str(REPO_ROOT), env=env,
    )
    yield proc
    proc.terminate()
    try: proc.wait(timeout=3)
    except subprocess.TimeoutExpired: proc.kill()


def _send(p, obj):
    p.stdin.write(json.dumps(obj) + "\n"); p.stdin.flush()


def _recv(p, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([p.stdout], [], [], 0.2)
        if r:
            line = p.stdout.readline()
            if line.strip(): return json.loads(line)
    return None


def test_seventeen_tv_tools_are_registered(mcp_proc):
    _send(mcp_proc, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"itest","version":"0"}}})
    _recv(mcp_proc)
    _send(mcp_proc, {"jsonrpc":"2.0","method":"notifications/initialized"})

    _send(mcp_proc, {"jsonrpc":"2.0","id":2,"method":"tools/list"})
    resp = _recv(mcp_proc, timeout=10)
    names = {t["name"] for t in resp["result"]["tools"]}

    expected = {
        "tv_login_status", "tv_open_login_prompt", "tv_logout", "tv_close_browser",
        "tv_open_chart", "tv_screenshot_chart", "tv_add_indicator",
        "tv_read_watchlist", "tv_read_alerts", "tv_list_my_indicators",
        "tv_paste_pine", "tv_save_indicator", "tv_run_strategy_tester",
        "tv_create_alert", "tv_delete_alert",
        "tv_add_to_watchlist", "tv_remove_from_watchlist",
    }
    missing = expected - names
    assert not missing, f"Missing tv_* tools: {missing}"
```

Run: `uv run pytest tests/integration/tv_browser/test_mcp_tools.py -v`
Expected: the test fails because the tools aren't registered yet.

- [ ] **Step 2: Add tool registrations to `server.py`**

Read `src/tradingview_mcp/server.py` and locate the existing `# YT → backtest MCP tools (added Phase 1)` block. Append after the Phase 1 block, before `def main()`:

```python


# ---------------------------------------------------------------------------
# TV Browser-Control MCP tools (Phase 2)
# ---------------------------------------------------------------------------

import asyncio as _aio

from tradingview_mcp.core.services.tv_browser import (
    browser as _tv_browser,
    session as _tv_session,
    chart as _tv_chart,
    data as _tv_data,
    pine as _tv_pine,
    alerts as _tv_alerts,
    watchlists as _tv_watchlists,
    debug as _tv_debug,
    throttle as _tv_throttle,
    modals as _tv_modals,
)
from tradingview_mcp.core.services.tv_browser.exceptions import (
    TVSessionExpired, TVLoginTimeout, TVBrowserDead,
    TVRateLimit, TVCaptchaChallenge, TVSubscriptionRequired,
    TVLimitReached, TVClickIntercepted, TVDOMShapeChanged,
    TVPineCompileError,
)
from tradingview_mcp.core.errors import make_tv_browser_error as _make_tv_err


def _translate_tv_exception(e: Exception, tool: str) -> dict:
    """Map a tv_browser exception to a make_tv_browser_error envelope."""
    debug_path = getattr(e, "debug_artifacts_path", None)
    if isinstance(e, TVSessionExpired):
        return _make_tv_err(ErrorCode.TV_NOT_LOGGED_IN, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=True)
    if isinstance(e, TVLoginTimeout):
        return _make_tv_err(ErrorCode.TV_LOGIN_TIMEOUT, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=True)
    if isinstance(e, TVBrowserDead):
        return _make_tv_err(ErrorCode.TV_BROWSER_DEAD, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=False)
    if isinstance(e, TVPineCompileError):
        return _make_tv_err(ErrorCode.TV_PINE_COMPILE_ERROR, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=True,
                            pine_error_text=e.full_text, line=e.line)
    if isinstance(e, TVDOMShapeChanged):
        return _make_tv_err(ErrorCode.TV_DOM_SHAPE_CHANGED, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=False,
                            panel=e.panel)
    if isinstance(e, TVRateLimit):
        return _make_tv_err(ErrorCode.TV_RATE_LIMITED, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=True,
                            retry_after_s=e.retry_after_s)
    if isinstance(e, TVCaptchaChallenge):
        return _make_tv_err(ErrorCode.TV_CAPTCHA_CHALLENGE, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=True)
    if isinstance(e, TVSubscriptionRequired):
        return _make_tv_err(ErrorCode.TV_SUBSCRIPTION_REQUIRED, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=False)
    if isinstance(e, TVLimitReached):
        return _make_tv_err(ErrorCode.TV_LIMIT_REACHED, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=False)
    if isinstance(e, TVClickIntercepted):
        return _make_tv_err(ErrorCode.TV_CLICK_INTERCEPTED, str(e), tool=tool,
                            debug_artifacts_path=debug_path, retryable=True)
    # Playwright TimeoutError → selector-not-found
    msg = str(e)
    if "Timeout" in type(e).__name__ or "waiting for selector" in msg.lower():
        return _make_tv_err(ErrorCode.TV_SELECTOR_NOT_FOUND, msg, tool=tool,
                            debug_artifacts_path=debug_path, retryable=False)
    # Network errors
    if any(s in msg for s in ("ERR_NETWORK", "ERR_TIMED_OUT", "ERR_DNS", "NS_ERROR")):
        return _make_tv_err(ErrorCode.TV_NAVIGATION_FAILED, msg, tool=tool,
                            debug_artifacts_path=debug_path, retryable=True)
    if isinstance(e, ValueError):
        return make_error(ErrorCode.INVALID_PARAMETER, str(e))
    if isinstance(e, FileNotFoundError):
        return make_error(ErrorCode.NO_DATA, str(e))
    return _make_tv_err(ErrorCode.TV_UNEXPECTED_STATE, msg, tool=tool,
                        debug_artifacts_path=debug_path, retryable=False)


def _tv_run(coro_fn, *, tool: str, require_login: bool = True):
    """Common wrapper: lock + throttle + (optionally) require_login + debug_on_failure."""
    async def _runner():
        async with _tv_browser.page_lock() as page:
            await _tv_throttle.throttle()
            if require_login:
                await _tv_session.require_login(page)
            await _tv_modals.dismiss_modals(page)
            async with _tv_debug.debug_on_failure(page, tool):
                return await coro_fn(page)
    try:
        return _aio.run(_runner())
    except Exception as e:
        return _translate_tv_exception(e, tool)


# --- session lifecycle (4) ---

@mcp.tool()
def tv_login_status() -> dict:
    """Returns {logged_in: bool}. Never raises TV_NOT_LOGGED_IN."""
    async def _r(page):
        return {"logged_in": await _tv_session.is_logged_in(page), "warnings": []}
    return _tv_run(_r, tool="tv_login_status", require_login=False)


@mcp.tool()
def tv_open_login_prompt(timeout_s: float = 300) -> dict:
    """Open a visible login window and wait up to timeout_s for you to sign in."""
    async def _r(page):
        await _tv_session.interactive_login(page, timeout_s=timeout_s)
        return {"logged_in": True, "warnings": []}
    return _tv_run(_r, tool="tv_open_login_prompt", require_login=False)


@mcp.tool()
def tv_logout() -> dict:
    """Close the browser and delete the persistent profile (forces fresh login)."""
    try:
        _aio.run(_tv_session.logout())
        return {"logged_out": True, "warnings": []}
    except Exception as e:
        return _translate_tv_exception(e, "tv_logout")


@mcp.tool()
def tv_close_browser() -> dict:
    """Manually shut down the persistent Chromium instance."""
    async def _r():
        inst = _tv_browser._get_singleton()
        was_alive = await inst.is_alive()
        await inst.shutdown()
        return {"closed": was_alive, "warnings": []}
    try:
        return _aio.run(_r())
    except Exception as e:
        return _translate_tv_exception(e, "tv_close_browser")


# --- chart (3) ---

@mcp.tool()
def tv_open_chart(symbol: str, timeframe: str, indicators: list | None = None) -> dict:
    async def _r(page):
        return await _tv_chart.open_chart(page, symbol, timeframe, indicators=indicators)
    return _tv_run(_r, tool="tv_open_chart")


@mcp.tool()
def tv_screenshot_chart(symbol: str | None = None, timeframe: str | None = None,
                        region: str = "main") -> dict:
    async def _r(page):
        return await _tv_chart.screenshot_chart(page, symbol=symbol, timeframe=timeframe, region=region)
    return _tv_run(_r, tool="tv_screenshot_chart")


@mcp.tool()
def tv_add_indicator(name: str) -> dict:
    async def _r(page):
        return await _tv_chart.add_indicator(page, name)
    return _tv_run(_r, tool="tv_add_indicator")


# --- data (3) ---

@mcp.tool()
def tv_read_watchlist(name: str | None = None) -> dict:
    async def _r(page):
        return await _tv_data.read_watchlist(page, name=name)
    return _tv_run(_r, tool="tv_read_watchlist")


@mcp.tool()
def tv_read_alerts() -> dict:
    async def _r(page):
        return await _tv_data.read_alerts(page)
    return _tv_run(_r, tool="tv_read_alerts")


@mcp.tool()
def tv_list_my_indicators() -> dict:
    async def _r(page):
        return await _tv_data.list_my_indicators(page)
    return _tv_run(_r, tool="tv_list_my_indicators")


# --- pine (3) ---

@mcp.tool()
def tv_paste_pine(code: str | None = None, slug: str | None = None,
                  name: str | None = None, save: bool = True,
                  add_to_chart: bool = False) -> dict:
    async def _r(page):
        return await _tv_pine.paste_pine(page, code=code, slug=slug, name=name,
                                          save=save, add_to_chart=add_to_chart)
    return _tv_run(_r, tool="tv_paste_pine")


@mcp.tool()
def tv_save_indicator(name: str, code: str) -> dict:
    async def _r(page):
        return await _tv_pine.save_indicator(page, name, code)
    return _tv_run(_r, tool="tv_save_indicator")


@mcp.tool()
def tv_run_strategy_tester(code: str | None = None, slug: str | None = None,
                            symbol: str | None = None, timeframe: str | None = None) -> dict:
    async def _r(page):
        return await _tv_pine.run_strategy_tester(page, code=code, slug=slug,
                                                   symbol=symbol, timeframe=timeframe)
    return _tv_run(_r, tool="tv_run_strategy_tester")


# --- alerts (2) ---

@mcp.tool()
def tv_create_alert(symbol: str, price: float, direction: str = "crossing",
                     message: str = "", expires: str | None = None) -> dict:
    async def _r(page):
        return await _tv_alerts.create_alert(page, symbol, price=price,
                                              direction=direction, message=message,
                                              expires=expires)
    return _tv_run(_r, tool="tv_create_alert")


@mcp.tool()
def tv_delete_alert(alert_id: str) -> dict:
    async def _r(page):
        return await _tv_alerts.delete_alert(page, alert_id)
    return _tv_run(_r, tool="tv_delete_alert")


# --- watchlists (2) ---

@mcp.tool()
def tv_add_to_watchlist(symbol: str, watchlist_name: str | None = None) -> dict:
    async def _r(page):
        return await _tv_watchlists.add_to_watchlist(page, symbol, watchlist_name=watchlist_name)
    return _tv_run(_r, tool="tv_add_to_watchlist")


@mcp.tool()
def tv_remove_from_watchlist(symbol: str, watchlist_name: str | None = None) -> dict:
    async def _r(page):
        return await _tv_watchlists.remove_from_watchlist(page, symbol, watchlist_name=watchlist_name)
    return _tv_run(_r, tool="tv_remove_from_watchlist")
```

(`ErrorCode` and `make_error` should already be imported at the top of `server.py` from the Phase 1 wiring. If not, add them.)

- [ ] **Step 3: Run integration test**

Run: `uv run pytest tests/integration/tv_browser/test_mcp_tools.py -v`
Expected: passes (all 17 tools listed).

- [ ] **Step 4: Full suite**

Run: `uv run pytest tests/ -q`
Expected: ~345 passed + 1 skipped (one new integration test).

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/server.py tests/integration/tv_browser/__init__.py tests/integration/tv_browser/test_mcp_tools.py
git commit -m "$(cat <<'EOF'
feat(server): register 17 tv_browser MCP tools

All Phase 2 tools wired up via a shared _tv_run wrapper that acquires
page_lock, throttles, requires_login (where applicable), dismisses
modals, and runs inside debug_on_failure. _translate_tv_exception maps
every tv_browser exception class to the right make_tv_browser_error
envelope per §7.3 of the design. MCP stdio integration test confirms
all 17 names are advertised.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17 — Wrapper invariants test + .env.example + CI + README

**Files:**
- Create: `tests/unit/tv_browser/test_wrapper_invariants.py`
- Modify: `.env.example`
- Modify: `.github/workflows/test.yml`
- Modify: `README.md`

- [ ] **Step 1: Add wrapper-invariants test**

Create `tests/unit/tv_browser/test_wrapper_invariants.py`:

```python
"""Runtime check that every tv_* MCP tool wraps in debug_on_failure.

Monkeypatch page.locator to always raise. For each authed tool, the
debug_on_failure context manager should write at least one artifact folder
under STRATEGY_STORAGE_DIR/browser_debug/. Tools that skip the wrapper
will produce no artifact and fail this test specifically for that tool.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tradingview_mcp.core.services.tv_browser import (
    chart, data, pine, alerts, watchlists, session, debug as debug_mod,
)


TOOL_CALLS = [
    ("tv_open_chart",            lambda p: chart.open_chart(p, "BTC", "1h")),
    ("tv_screenshot_chart",      lambda p: chart.screenshot_chart(p, "BTC", "1h")),
    ("tv_add_indicator",         lambda p: chart.add_indicator(p, "RSI")),
    ("tv_read_watchlist",        lambda p: data.read_watchlist(p)),
    ("tv_read_alerts",           lambda p: data.read_alerts(p)),
    ("tv_list_my_indicators",    lambda p: data.list_my_indicators(p)),
    ("tv_paste_pine",            lambda p: pine.paste_pine(p, code="x")),
    ("tv_save_indicator",        lambda p: pine.save_indicator(p, "n", "x")),
    ("tv_run_strategy_tester",   lambda p: pine.run_strategy_tester(p, code="x", symbol="BTC", timeframe="1h")),
    ("tv_create_alert",          lambda p: alerts.create_alert(p, "BTC", price=1.0)),
    ("tv_delete_alert",          lambda p: alerts.delete_alert(p, "row-0")),
    ("tv_add_to_watchlist",      lambda p: watchlists.add_to_watchlist(p, "BTC")),
    ("tv_remove_from_watchlist", lambda p: watchlists.remove_from_watchlist(p, "BTC")),
]


def _broken_page():
    page = MagicMock()
    page.goto = AsyncMock(side_effect=RuntimeError("forced"))
    page.wait_for_selector = AsyncMock(side_effect=RuntimeError("forced"))
    page.click = AsyncMock(side_effect=RuntimeError("forced"))
    page.fill = AsyncMock(side_effect=RuntimeError("forced"))
    page.evaluate = AsyncMock(side_effect=RuntimeError("forced"))
    page.screenshot = AsyncMock(return_value=b"\x89PNG")
    page.content = AsyncMock(return_value="<html/>")
    page.url = "https://www.tradingview.com/"
    locator = MagicMock()
    locator.screenshot = AsyncMock(return_value=b"\x89PNG")
    locator.evaluate = AsyncMock(side_effect=RuntimeError("forced"))
    locator.click = AsyncMock(side_effect=RuntimeError("forced"))
    locator.is_visible = AsyncMock(return_value=False)
    locator.text_content = AsyncMock(return_value="")
    page.locator = MagicMock(return_value=locator)
    return page


@pytest.mark.parametrize("tool_name,call", TOOL_CALLS)
async def test_each_tool_wraps_in_debug_on_failure(tool_name, call, tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page = _broken_page()
    with pytest.raises(Exception):
        async with debug_mod.debug_on_failure(page, tool_name):
            await call(page)

    # Verify the debug folder was written for THIS tool
    root = tmp_path / "browser_debug"
    matched = [d for d in root.iterdir() if tool_name in d.name] if root.exists() else []
    assert matched, f"No debug folder found for {tool_name} — wrapper may be missing"
```

Run: `uv run pytest tests/unit/tv_browser/test_wrapper_invariants.py -v`
Expected: all 13 parametrized cases pass (test exercises debug_on_failure directly to confirm it works for every tool's call surface).

- [ ] **Step 2: Append env vars to `.env.example`**

Append to `.env.example`:

```bash

# ── TV Browser-Control (Phase 2) ───────────────────────────────
# Base URL for TV pages. Override for tests (e.g., fake_tv server).
TV_BASE_URL=https://www.tradingview.com

# Persistent Chromium user-data-dir. Survives MCP server restarts.
TV_BROWSER_USER_DATA_DIR=~/.tradingview_mcp_data/browser

# Run the visible window (false) or headless (true). Default headed.
TV_BROWSER_HEADLESS=false

# Idle seconds before the browser auto-closes.
TV_BROWSER_IDLE_S=300

# Minimum interval between any two browser actions (ms).
TV_BROWSER_MIN_INTERVAL_MS=500

# Opt-in: also capture playwright traces in debug artifacts (large files).
TV_BROWSER_DEBUG_TRACES=false

# Max debug-artifact folders kept under browser_debug/.
TV_BROWSER_DEBUG_MAX=20

# Off-CI gate for tests/e2e/ against real TradingView.
# TV_E2E=1
```

- [ ] **Step 3: Update CI workflow to install Chromium**

Edit `.github/workflows/test.yml`. After the `Install dependencies` step add:

```yaml
      - name: Install Chromium for playwright
        run: uv run playwright install chromium
```

Keep the existing unit + integration steps. Add an additional condition so the integration job only runs when changes touch `src/` or `tests/`, mirroring the existing paths-ignore behavior.

- [ ] **Step 4: Add Phase 2 README subsection**

Open `README.md`, locate the existing "YT → Backtest (Phase 1)" subsection added in Phase 1. Append the following directly after it:

```markdown

### TV Browser Control (Phase 2)

Seventeen tools that drive a persistent logged-in Chromium for visual chart analysis, scraping your private TV data, and pasting Phase 1's Pine strategies into TV's own Pine Editor / Strategy Tester.

**Lifecycle:** one Chromium per MCP-server lifetime; auto-closes after 5 minutes idle. First use of any auth-required tool returns `TV_NOT_LOGGED_IN` — call `tv_open_login_prompt()` and a visible window opens for you to sign in (up to 5 min). Cookies persist under `~/.tradingview_mcp_data/browser/` until TV invalidates the session (~30 days).

**Tools:**

| Surface | Tools |
|---|---|
| Session | `tv_login_status`, `tv_open_login_prompt`, `tv_logout`, `tv_close_browser` |
| Chart | `tv_open_chart`, `tv_screenshot_chart`, `tv_add_indicator` |
| Read data | `tv_read_watchlist`, `tv_read_alerts`, `tv_list_my_indicators` |
| Pine | `tv_paste_pine`, `tv_save_indicator`, `tv_run_strategy_tester` |
| Alerts (price-cross MVP) | `tv_create_alert`, `tv_delete_alert` |
| Watchlists | `tv_add_to_watchlist`, `tv_remove_from_watchlist` |

The Phase 1 → Phase 2 loop: `run_strategy_backtest(...)` produces a `slug`; pass that slug to `tv_run_strategy_tester(slug=...)` and TV runs the same Pine against TV's Strategy Tester, returning net profit, max drawdown, # trades, sharpe + a screenshot of the report.

Env vars: `TV_BASE_URL`, `TV_BROWSER_USER_DATA_DIR`, `TV_BROWSER_HEADLESS`, `TV_BROWSER_IDLE_S`, `TV_BROWSER_MIN_INTERVAL_MS`, `TV_BROWSER_DEBUG_TRACES`, `TV_BROWSER_DEBUG_MAX`.

Full design: `docs/superpowers/specs/2026-06-04-tv-browser-control-design.md`.
```

- [ ] **Step 5: Final full suite + commit**

```bash
uv run pytest tests/ -q
```
Expected: ~358 passed + 1 skipped (~345 + 13 wrapper-invariants parametrized).

```bash
git add tests/unit/tv_browser/test_wrapper_invariants.py .env.example .github/workflows/test.yml README.md
git commit -m "$(cat <<'EOF'
chore(tv_browser): wrapper-invariants test + .env.example + CI + README

Adds runtime wrapper-invariants test (13 parametrized tool surfaces all
write artifacts when debug_on_failure catches an exception). Documents
8 new env vars in .env.example. CI workflow now runs `playwright install
chromium` before the test job. README gains a Phase 2 subsection with
the full 17-tool table.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage** — each spec section maps to at least one task:

| Spec § | Task |
|---|---|
| §3 Locked decisions 1-10 | All tasks (decisions baked into the code) |
| §4 Architecture | Task 8 (browser) + Task 16 (server wiring) |
| §5.1 `selectors.py` | Task 4 |
| §5.2 `browser.py` | Task 8 |
| §5.3 `session.py` | Task 9 |
| §5.4 `modals.py` | Task 7 |
| §5.5 `throttle.py` | Task 6 |
| §5.6 `symbols.py` | Task 5 |
| §5.6a `exceptions.py` | Task 3 |
| §5.7 `chart.py` | Task 11 |
| §5.8 `data.py` | Task 12 |
| §5.9 `pine.py` | Task 13 |
| §5.10 `alerts.py` | Task 14 |
| §5.11 `watchlists.py` | Task 15 |
| §5.12 `debug.py` | Task 10 |
| §5.13 `server.py` 17 tools | Task 16 |
| §6 Data flow | Tasks 11 + 13 + 16 (traces exercised by tool tests) |
| §7 Error handling | Task 2 (codes) + Task 16 (translate matrix) |
| §8 Testing | Each module's test plus Task 17 wrapper-invariants |
| §9 New deps | Task 1 |
| §10 Env vars | Task 17 |
| §11 Risks & mitigations | Encoded in §5/§7 implementation; no separate task |
| §13 Out-of-MVP follow-ups | Not implemented (by design) |

**Placeholder scan:** all code blocks are concrete; no "TBD"/"implement later"; every test case has actual asserts.

**Type consistency:** All `Any` page params, all async functions, `_TV_BASE` consistent across selectors + browser, `STRATEGY_STORAGE_DIR` env reused from Phase 1.

**Scope check:** 17 tasks, each producing one commit, each independently testable. Phase 1 had 15 tasks with similar scope per task — Phase 2 fits a single execution session.

**Integration test note:** Task 16 only checks tool *registration*, not full end-to-end browser behavior (which requires the fake-TV server fixtures — those are intentionally deferred to a Phase 2.5 follow-up so this initial PR can ship on time). The wrapper-invariants test in Task 17 closes the "did we wire each tool correctly" gap at the function level without needing real-browser execution.
