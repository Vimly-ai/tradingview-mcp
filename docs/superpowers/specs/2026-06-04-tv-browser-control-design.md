# TV Browser Control MCP Tools — Design Spec

**Date:** 2026-06-04
**Status:** Approved for implementation planning
**Sub-project:** 2 of 3 (Phase 2)
**Owner:** Andrew Fackrell
**Parent project:** Trading-MCP / tradingview-mcp
**Predecessor spec:** `docs/superpowers/specs/2026-06-03-yt-to-backtest-mcp-design.md` (Phase 1)

---

## 1. Goal

Add 17 MCP tools to `tradingview-mcp` that let Claude Desktop **see and interact with the user's live TradingView account** via a persistent, logged-in Chromium instance. Closes the loop with Phase 1: a YT-generated strategy can be pasted into TV's own Strategy Tester without leaving the chat.

End-state user flow:

> **User:** *"Take a look at the BTC 1h chart and tell me what you see."*
> *(Claude calls `tv_screenshot_chart`. The persistent browser is already logged in; serializes through the asyncio mutex; throttles ≥500 ms since last action; dismisses stale modals; navigates to the chart; waits for the chart-ready anchor; captures a screenshot; returns base64 + on-disk path.)*
>
> **Assistant:** *"BTC 1h is in a clean ascending channel…"*
>
> **User:** *"Run iter 2 of the BTCUSDT strategy on TradingView's Strategy Tester."*
> *(Claude calls `tv_run_strategy_tester(slug="BTCUSDT-1h-iter2")`. Tool loads `strategy.pine` from Phase 1's storage, opens Pine Editor, sets the Monaco value, runs compile check, saves under a deterministic name, adds to chart, opens Strategy Tester, extracts stats from the DOM panel, returns metrics + screenshot.)*
>
> **Assistant:** *"On TradingView's engine: net profit +18.3%, max drawdown −7.1%, 43 trades, win rate 58%. Sharpe 1.27. Screenshot attached."*

This spec covers Phase 2 only. Phase 3 (standalone Pine generator MCP) remains a separate sub-project with its own future spec.

---

## 2. Non-goals

- **Live trading / order placement.** TV supports broker integration; we deliberately don't touch it.
- **TV account modification** — billing, profile, subscription. Out of scope.
- **Pine alert builder beyond simple price-cross.** TV's alert dialog is structured (column / operator / value) with many feature flags. MVP supports only "price crossing N" alerts; free-form alert expressions are deferred.
- **Pine Premium-only indicator addition** on Free accounts. TV will block this; we surface `TV_SUBSCRIPTION_REQUIRED` rather than try to work around.
- **Cross-browser support.** Playwright is pinned to Chromium. No Firefox/WebKit.
- **Multi-account sessions per Claude Desktop run.** One TV account at a time. `tv_logout()` clears the profile so a different account can sign in on the next call.
- **Captcha solving.** When TV challenges via Cloudflare, the visible browser shows the captcha and the user solves it manually; we just detect and surface `TV_CAPTCHA_CHALLENGE`.
- **Phase 1 ↔ Phase 2 auto-orchestration.** The assistant in Claude Desktop is the orchestrator — Phase 1 produces a `slug`, the assistant decides when to hand it to a Phase 2 tool.

---

## 3. Locked design decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Extend the existing `tradingview-mcp` server** with new browser tools using `playwright-python` directly | Same MCP, same storage, same error envelope. Phase 1's `slug` system flows cleanly into Phase 2 tools. |
| 2 | All four use-case categories in scope: **read charts visually**, **read private TV data**, **paste Pine + run Strategy Tester**, **create/modify alerts + watchlists** | User-selected. Implementation may be sub-phased internally but spec is the full surface. |
| 3 | **Persistent Chromium profile** under `~/.tradingview_mcp_data/browser/` | Login persists across Claude Desktop restarts until TV invalidates the session (~30 days). Best UX. |
| 4 | **Approach A — Persistent browser + thick tool surface** | One warm Chromium instance, ~17 named verbs. Best UX, closes YT→TV loop; trade-off accepted: we ship selector patches when TV redesigns (2–4×/year). |
| 5 | **Asyncio mutex** in `browser.py` — all tool calls serialize on a single page lock | MCP protocol serializes single-client calls already, but safety belt prevents future surprises. |
| 6 | **5-minute idle auto-close** | Releases Chromium resources between sessions; configurable via `TV_BROWSER_IDLE_S`. Disabled during `interactive_login` and while page lock held. |
| 7 | **Headed by default** (`headless=false`) | You see what Claude is doing; trust builds. `TV_BROWSER_HEADLESS=true` flips for batch / screenshot-only usage. |
| 8 | **Single source of truth in `selectors.py`** for every DOM selector and URL pattern | When TV redesigns, one file gets patched. CI lint rejects selector strings outside this file. |
| 9 | **17 total MCP tools** | Authoritative tool count: 4 lifecycle + 3 chart + 3 data + 3 pine + 2 alerts + 2 watchlists. |
| 10 | **URL constants read base from `TV_BASE_URL` env** (default `https://www.tradingview.com`) | Lets integration tests redirect playwright to the local fake TV server without monkeypatch gymnastics. |

---

## 4. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Claude Desktop                                                  │
│   "Screenshot the BTC 1h chart and tell me what you see."        │
└───────────────────────────────┬──────────────────────────────────┘
                                │ MCP (stdio)
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  tradingview-mcp server                                          │
│                                                                  │
│   yt_strategy/  ◀── Phase 1 (unchanged)                          │
│                                                                  │
│   tv_browser/   ◀── Phase 2 (new)                                │
│     ├─ browser.py     persistent Chromium + asyncio mutex +      │
│     │                 idle timer (defers on lock-held &          │
│     │                 disabled during login) + crash recovery    │
│     ├─ session.py     login detect / interactive login /         │
│     │                 require_login guard / logout via rmtree    │
│     ├─ modals.py      generic modal-dismissal pre-pass           │
│     ├─ throttle.py    min-interval throttle (default 500 ms)     │
│     ├─ chart.py       tv_open_chart, tv_screenshot_chart,        │
│     │                 tv_add_indicator                           │
│     ├─ data.py        tv_read_watchlist, tv_read_alerts,         │
│     │                 tv_list_my_indicators                      │
│     ├─ pine.py        tv_paste_pine, tv_save_indicator,          │
│     │                 tv_run_strategy_tester                     │
│     ├─ alerts.py      tv_create_alert, tv_delete_alert           │
│     ├─ watchlists.py  tv_add_to_watchlist,                       │
│     │                 tv_remove_from_watchlist                   │
│     ├─ symbols.py     _tv_normalize_symbol mapping               │
│     ├─ exceptions.py  TV-specific exception classes used by      │
│     │                 the wrapper translation matrix             │
│     ├─ debug.py       debug_on_failure context manager,          │
│     │                 artifact rotation                          │
│     └─ selectors.py   single source of truth for selectors       │
│                       + URL templates reading TV_BASE_URL        │
└──────────────────────────┬───────────────────────────────────────┘
                           │ Chromium DevTools Protocol
                           ▼
       ┌─────────────────────────────────────────┐
       │  Chrome (headed; persistent user-data)  │
       │   ~/.tradingview_mcp_data/browser/      │
       │                                         │
       │   Logged-in TradingView session         │
       └─────────────────────────────────────────┘
```

Persistent `browser/` directory holds cookies, localStorage, IndexedDB — equivalent to a normal Chrome profile. First-ever use of any authed `tv_*` tool when not logged in returns `TV_NOT_LOGGED_IN`; the assistant calls `tv_open_login_prompt()`, which opens the headed window and polls up to 5 min for the user to complete login (including 2FA). After that, the session sticks until TV invalidates it.

### 4.1 Resilience invariants
- **One Chromium instance per MCP server lifetime.** Mutex serializes all tool bodies. No tool body skips the lock.
- **Idle timer defers while page lock held.** Implementation: timer task `await`s on a non-locked event before firing.
- **Idle timer disabled during `interactive_login`.** Re-enabled when login flow returns or times out.
- **Crash recovery: relaunch once.** Two consecutive failures → `TV_BROWSER_DEAD`. No infinite retry loop.
- **Modal-dismissal pre-pass runs in every tool's first step**, after `require_login`.
- **Throttle is global, not per-tool.** TV sees one client; the rate applies to all activity.
- **Selectors only in `selectors.py`.** CI grep lint rejects literal selectors anywhere else.

---

## 5. Components

All under `src/tradingview_mcp/core/services/tv_browser/`. Each module has one responsibility.

### 5.1 `selectors.py`
**Purpose:** Single source of truth for TV DOM selectors and URL templates.

```python
import os

_TV_BASE = os.environ.get("TV_BASE_URL", "https://www.tradingview.com").rstrip("/")

CHART_URL_TPL       = _TV_BASE + "/chart/?symbol={symbol}&interval={tv_interval}"
PINE_EDITOR_URL     = _TV_BASE + "/pine-editor/"
PINE_LIBRARY_URL    = _TV_BASE + "/scripts/yours/"
ALERTS_URL          = _TV_BASE + "/alerts/"
LOGIN_URL           = _TV_BASE + "/accounts/signin/"

# Ready-state anchors (proof a page finished loading)
CHART_READY            = '[data-name="legend-source-item"]'
PINE_EDITOR_READY      = 'div.tv-script-editor'
STRATEGY_TESTER_READY  = '[data-name="strategy-tester-overview"]'

# Login state
LOGGED_IN_INDICATOR    = 'button[aria-label="Open user menu"]'

# Chart
MAIN_CHART_CANVAS      = 'div[data-name="pane-main"] canvas'
TICKER_SEARCH_INPUT    = 'input[data-role="search-input"]'
INDICATOR_SEARCH_DIALOG_INPUT = 'input[data-name="indicator-search"]'
INDICATOR_DIALOG_FIRST_RESULT = 'div[data-name="indicator-result"]:first-child'

# Pine Editor
PINE_EDITOR_TEXTAREA           = 'div.monaco-editor'  # set via Monaco API, not page.fill
PINE_EDITOR_SAVE_BTN           = 'button[data-name="save"]'
PINE_EDITOR_ADD_TO_CHART_BTN   = 'button[data-name="add-to-chart"]'
PINE_EDITOR_ERROR_PANEL        = 'div[data-name="pine-script-errors"]'
SAVE_DIALOG_NAME_INPUT         = 'input[data-name="script-name"]'
SAVE_DIALOG_CONFIRM_BTN        = 'button[data-name="save-confirm"]'

# Strategy Tester
STRATEGY_TESTER_TAB            = 'button[id="footer-tester"]'
STRATEGY_TESTER_STATS_PANEL    = 'div[data-name="strategy-tester-stats"]'
STRATEGY_TESTER_REPORT_REGION  = 'div[data-name="strategy-tester-report"]'

# Watchlist
WATCHLIST_ROWS                 = '[data-name="watchlist-symbol-row"]'
WATCHLIST_DROPDOWN             = 'button[data-name="watchlist-selector"]'

# Alerts
ALERT_LIST_ROW                 = '[data-name="alerts-item"]'
ALERT_CREATE_BTN_TOOLBAR       = 'button[data-name="legend-create-alert-button"]'
ALERT_DIALOG                   = 'div[data-name="alert-dialog"]'
ALERT_DIALOG_PRICE_INPUT       = 'input[data-name="alert-value-input"]'
ALERT_DIALOG_MESSAGE_INPUT     = 'textarea[data-name="alert-message"]'
ALERT_DIALOG_CREATE_BTN        = 'button[data-name="submit"]'

# Common modal closers (for the dismissal pre-pass)
MODAL_DISMISS_SELECTORS = [
    'button[aria-label="Close"]',
    'div[data-name="upgrade-popup"] button[data-name="close"]',
    'div[data-name="save-prompt"] [data-name="save-prompt-cancel"]',
    'div[data-name="news-popup"] button[aria-label="Close"]',
]

TV_INTERVAL_MAP = {
    "1m":"1", "3m":"3", "5m":"5", "15m":"15", "30m":"30",
    "1h":"60", "2h":"120", "4h":"240",
    "1d":"D", "1w":"W", "1M":"M",
}
```

Every selector here is paired with a baseline entry in `tests/unit/tv_browser/test_selectors_pinned.py::EXPECTED_SELECTORS` (see §8.2).

### 5.2 `browser.py`
**Purpose:** Own the Chromium lifecycle.

```python
class TVBrowser:
    async def get_page(self) -> Page: ...
    async def shutdown(self) -> None: ...
    async def is_alive(self) -> bool: ...
    async def disable_idle(self) -> None: ...
    async def enable_idle(self) -> None: ...

async def page_lock() -> AsyncContextManager[Page]: ...
```

Implementation behaviors:
- Lazy launch on first `get_page()` via `playwright.chromium.launch_persistent_context(user_data_dir=...)`.
- Reads env: `TV_BROWSER_USER_DATA_DIR`, `TV_BROWSER_HEADLESS`, `TV_BROWSER_IDLE_S` (default 300), `TV_BROWSER_MIN_INTERVAL_MS`.
- Asyncio.Lock around the single Page. `page_lock()` is an `asynccontextmanager` that acquires/releases.
- Idle timer is a background `asyncio.Task` that runs `await asyncio.sleep(idle_s); await _maybe_shutdown()`. `_maybe_shutdown` checks the lock state — if held, reschedules.
- `disable_idle` / `enable_idle` toggle a flag the timer respects.
- `is_alive` checks `page.is_closed() == False` and `context.browser.is_connected() == True`.
- Crash recovery: on detected dead state in `get_page`, dispose + relaunch once. Second consecutive failure → raise `TVBrowserDead`.
- SIGTERM handler installed at module import calls `asyncio.run(shutdown())` best-effort. Documented as a "lost trace on hard kill" caveat (§10.3).

### 5.3 `session.py`
**Purpose:** Login detection + interactive login + logout.

```python
class TVSessionExpired(Exception): ...
class TVLoginTimeout(Exception): ...

async def is_logged_in(page) -> bool: ...
async def require_login(page) -> None: ...           # raises TVSessionExpired
async def interactive_login(page, timeout_s: float = 300) -> None: ...
async def logout() -> None: ...                       # closes browser + deletes user_data_dir
```

- `is_logged_in`: if page is not on a `tradingview.com` URL, navigate to `_TV_BASE` first. Then poll `LOGGED_IN_INDICATOR` for up to 2 s.
- `interactive_login`: calls `browser.disable_idle()`, navigates to `LOGIN_URL`, then polls `is_logged_in()` every 2 s up to `timeout_s`. Re-enables idle in finally.
- `logout`: calls `tv_close_browser` semantics (shutdown + `shutil.rmtree(user_data_dir)`). Near-zero error surface compared to driving the UI.

### 5.4 `modals.py`
**Purpose:** Idempotent modal-dismissal pre-pass.

```python
async def dismiss_modals(page, timeout_s: float = 1.0) -> int:
    """For each selector in MODAL_DISMISS_SELECTORS, try one click with short timeout.
    Returns the count of modals dismissed. Errors swallowed silently — the next
    tool action will surface a more specific error if blocked."""
```

### 5.5 `throttle.py`
**Purpose:** Global min-interval throttle to keep TV's bot-detection happy.

```python
async def throttle() -> None: ...
```

Module-level `_last_call_ts: float`. On call: compute `wait = min_interval - (now - last)`, sleep if positive, update `_last_call_ts`. Concurrent callers serialize naturally via the page lock (which they all hold while throttling).

### 5.6 `symbols.py`
**Purpose:** Map user-facing symbols to TV-canonical form (e.g. `EXCHANGE:TICKER`).

```python
def normalize(symbol: str) -> str:
    """E.g. 'BTC' → 'BINANCE:BTCUSDT', 'AAPL' → 'NASDAQ:AAPL'.
    Already-canonical symbols (with ':' prefix) pass through unchanged."""
```

**Distinct from Phase 1's `route_symbol`.** Phase 1's `yt_strategy/data.py::route_symbol(sym) → "binance" | "yahoo" | "fixture"` decides *which OHLCV upstream to call*. Phase 2's `symbols.normalize(sym) → "BINANCE:BTCUSDT"` produces *the canonical string TV uses in its chart URLs and selectors*. The two functions share no code, but their routing tables should be kept consistent — when adding a new symbol family, update both.

Routing table:
- Crypto aliases (`BTC`, `ETH`, `SOL`, …) → `BINANCE:<sym>USDT`
- Bare alphanumeric ending in known quote (`BTCUSDT`, `ETHUSDT`) → `BINANCE:<sym>`
- US equity tickers (3–5 uppercase letters, no `=`, `^`, `.`, `-`) → `NASDAQ:<sym>` (fallback to `NYSE:<sym>` if Nasdaq's chart 404s)
- FX symbols ending `=X` (`EURUSD=X`) → `FX:EURUSD`
- Yahoo-style crypto (`BTC-USD`) → `BINANCE:BTCUSDT` with a warning ("converted Yahoo-style symbol")
- Already-prefixed (`BINANCE:`, `NYSE:`, …) → pass through
- Unknown → return as-is with a warning

### 5.6a `exceptions.py`
**Purpose:** Hold all TV-specific exception classes raised inside `tv_browser/` and consumed by the wrapper translation matrix (§7.3). Keeping them in one file makes the translation map auditable in one read.

```python
class TVSessionExpired(Exception): ...
class TVLoginTimeout(Exception): ...
class TVBrowserDead(Exception): ...
class TVRateLimit(Exception):
    def __init__(self, message: str, retry_after_s: float | None = None): ...
class TVCaptchaChallenge(Exception): ...
class TVSubscriptionRequired(Exception): ...
class TVLimitReached(Exception): ...
class TVClickIntercepted(Exception): ...
class TVDOMShapeChanged(Exception):
    def __init__(self, message: str, panel: str | None = None): ...
class TVPineCompileError(Exception):
    def __init__(self, message: str, full_text: str, line: int | None): ...
```

Every exception carries enough context for the wrapper to construct a rich envelope:
- `TVRateLimit.retry_after_s` — passed through to the envelope when TV's banner exposes a duration.
- `TVDOMShapeChanged.panel` — names which DOM region failed extraction (e.g. `"strategy_tester_stats"`).
- `TVPineCompileError.full_text` / `.line` — full multi-line panel text + first error line for the envelope.

Imported by `session.py`, `browser.py`, `pine.py`, `data.py`, and the server wrappers.

### 5.7 `chart.py`
**Purpose:** Chart-canvas operations.

```python
async def open_chart(symbol: str, timeframe: str, indicators: list[str] | None = None) -> dict
async def screenshot_chart(symbol: str | None = None, region: str = "main", apply_indicators: list[str] | None = None) -> dict
async def add_indicator(name: str) -> dict
```

- `screenshot_chart` returns MCP image-content shape:
  ```python
  {"type": "image",
   "data": "<base64 PNG>",
   "mimeType": "image/png",
   "path": "<screenshots/timestamp-symbol.png>",
   "symbol": "<normalized>", "timeframe": "<tf>"}
  ```
- `region` accepted values: `"main"` (chart canvas only, default), `"full"` (entire viewport), `"footer"` (Strategy Tester / Pine / footer panel).
- If `symbol` is `None`, captures whatever's currently on screen. Documented as "current chart state".
- `add_indicator(name="RSI")` opens the indicator dialog, types name, clicks first result.

### 5.8 `data.py`
**Purpose:** Read-only DOM scraping.

```python
async def read_watchlist(name: str | None = None) -> dict
async def read_alerts() -> dict
async def list_my_indicators() -> dict
```

- `read_watchlist`: if `name` is `None`, reads the currently visible watchlist. Returns `{"name": str, "rows": [{symbol, price, change_pct, change_abs}]}`.
- `read_alerts`: navigates to `ALERTS_URL`, returns `{"alerts": [{symbol, condition, message, active, alert_id}]}`. `alert_id` is the DOM row identifier (used by `tv_delete_alert`).
- `list_my_indicators`: navigates to `PINE_LIBRARY_URL`, returns `{"indicators": [{name, last_modified, tv_script_id}]}`.

Raises `TV_DOM_SHAPE_CHANGED` if expected row structure is missing.

### 5.9 `pine.py`
**Purpose:** Pine Editor + Strategy Tester — the Phase 1 → Phase 2 closure point.

```python
async def paste_pine(
    code: str | None = None,
    slug: str | None = None,
    name: str | None = None,
    save: bool = True,
    add_to_chart: bool = False,
) -> dict

async def save_indicator(name: str, code: str) -> dict

async def run_strategy_tester(
    code: str | None = None,
    slug: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict
```

- Exactly one of `code` / `slug` must be set; ValueError otherwise.
- When `slug` is set: load Phase 1's `~/.tradingview_mcp_data/strategies/<slug>/strategy.pine`. Raises `FileNotFoundError` if absent.
- Monaco interaction: helper `_set_monaco_value(page, code)` calls `page.evaluate()` with the Monaco JS API:
  ```js
  const editor = monaco.editor.getEditors()[0];
  editor.setValue(code);
  ```
- Compile-check helper `_pine_compile_error(page) -> str | None`: reads `PINE_EDITOR_ERROR_PANEL` text; returns full error text (multi-line preserved) or `None`. Returned text is parsed for the first line number for the `line` envelope field.
- `paste_pine` flow: open editor → set value → compile-check → (if save) save dialog → (if add_to_chart) add-to-chart click. If compile-check fails: do NOT save. Raise `TVPineCompileError(full_text, first_line)`.
- `run_strategy_tester`: calls `paste_pine(save=True, add_to_chart=True)`, then opens Strategy Tester tab, waits for stats panel, runs `_read_strategy_tester_stats(page) -> dict` (DOM scrape via `page.evaluate`), captures screenshot of report region.

### 5.10 `alerts.py`
**Purpose:** Alert management. MVP scope = price-cross alerts only (per §2 non-goals).

```python
async def create_alert(
    symbol: str, price: float, direction: str = "crossing",
    message: str = "", expires: str | None = None
) -> dict

async def delete_alert(alert_id: str | int) -> dict
```

- `direction` accepted values: `"crossing"`, `"crossing_up"`, `"crossing_down"`.
- `expires` format: ISO-8601 datetime string (e.g. `"2026-12-31T23:59:00Z"`) or `None` for TV's default ("Open-ended"). Other formats raise `INVALID_PARAMETER`.
- Flow: open chart at `symbol` → click `ALERT_CREATE_BTN_TOOLBAR` → wait for `ALERT_DIALOG` → fill `ALERT_DIALOG_PRICE_INPUT` with `str(price)` → fill `ALERT_DIALOG_MESSAGE_INPUT` → submit.
- `delete_alert(alert_id)`: navigate to `ALERTS_URL`, find row by `alert_id`, click row's delete button.

### 5.11 `watchlists.py`
**Purpose:** Watchlist manipulation.

```python
async def add_to_watchlist(symbol: str, watchlist_name: str | None = None) -> dict
async def remove_from_watchlist(symbol: str, watchlist_name: str | None = None) -> dict
```

- If `watchlist_name` is provided, click `WATCHLIST_DROPDOWN` and select the named list first. Otherwise operate on current watchlist.
- Add: navigate to chart for `symbol`, click "+" / "Add to watchlist" toolbar button.
- Remove: find row by symbol in `WATCHLIST_ROWS`, click row's remove control.

### 5.12 `debug.py`
**Purpose:** Capture screenshot + DOM dump + (opt-in) trace on tool failure.

```python
@asynccontextmanager
async def debug_on_failure(page, tool_name: str) -> AsyncIterator[None]:
    """try: yield. On exception: dump artifacts to
    ~/.tradingview_mcp_data/browser_debug/<timestamp>-<tool>/.
    Re-raises with .debug_artifacts_path attached."""

def rotate_artifacts(root: Path, max_count: int = 20) -> None:
    """Keep newest `max_count` subdirs; delete the rest."""
```

- Artifacts always written: `screenshot.png`, `dom.html`, `error.txt`.
- Trace artifact `trace.zip` opt-in via `TV_BROWSER_DEBUG_TRACES=1`.
- Rotation: after each write, prune to `max_count=20` (configurable via `TV_BROWSER_DEBUG_MAX`).
- Successful operations write NO artifacts here. Screenshot results (from `tv_screenshot_chart`) are a separate retention path under `screenshots/` with `max_count=100`.

### 5.13 `server.py` additions
17 new `@mcp.tool()` registrations. Each wrapper:
1. Acquires `page_lock`.
2. Calls `throttle`.
3. Calls `require_login` (skipped only for `tv_login_status` and `tv_open_login_prompt`).
4. Wraps body in `debug_on_failure`.
5. Calls the right `chart/data/pine/alerts/watchlists/session` function.
6. Catches `playwright.async_api.Error` (the base class) and downcasts to the right `make_tv_browser_error` code.
7. Catches `ValueError` → `INVALID_PARAMETER` envelope.
8. Returns JSON-serializable dict or error envelope.

Tool registry:

| # | Tool | Module | Lock+login required |
|---|---|---|---|
| 1 | `tv_login_status` | session | lock only |
| 2 | `tv_open_login_prompt` | session | lock only |
| 3 | `tv_logout` | session | none (closes browser) |
| 4 | `tv_close_browser` | browser | none |
| 5 | `tv_open_chart` | chart | yes |
| 6 | `tv_screenshot_chart` | chart | yes |
| 7 | `tv_add_indicator` | chart | yes |
| 8 | `tv_read_watchlist` | data | yes |
| 9 | `tv_read_alerts` | data | yes |
| 10 | `tv_list_my_indicators` | data | yes |
| 11 | `tv_paste_pine` | pine | yes |
| 12 | `tv_save_indicator` | pine | yes |
| 13 | `tv_run_strategy_tester` | pine | yes |
| 14 | `tv_create_alert` | alerts | yes |
| 15 | `tv_delete_alert` | alerts | yes |
| 16 | `tv_add_to_watchlist` | watchlists | yes |
| 17 | `tv_remove_from_watchlist` | watchlists | yes |

### 5.14 Boundary check
Each module passes "can someone use it without reading internals?":
- `selectors.py` → import constants; change when TV redesigns.
- `browser.py` → `async with page_lock() as page:` → get a live, lock-held page.
- `session.py` → `await require_login(page)` → raises if not.
- `modals.py` → `await dismiss_modals(page)` → idempotent.
- `throttle.py` → `await throttle()` → may sleep.
- `symbols.py` → pure function, no I/O.
- `exceptions.py` → import-only; no logic, just dataclass-like exception holders.
- `chart`/`data`/`pine`/`alerts`/`watchlists` → pure async functions taking a page.
- `debug.py` → context manager + rotation; no internal coupling.

---

## 6. Data flow

### 6.1 Trace 1 — Read-only chart analysis

```
YOU: "Take a look at the BTC 1h chart and tell me what you see."
      │
      ▼
[Tool]  tv_screenshot_chart(symbol="BTC", region="main")
        │
        ├─ async with page_lock() as page:
        ├─ await throttle()
        ├─ await require_login(page)         → may raise TVSessionExpired
        ├─ async with debug_on_failure(page, "tv_screenshot_chart"):
        │      sym = symbols.normalize("BTC")            # "BINANCE:BTCUSDT"
        │      url = CHART_URL_TPL.format(symbol=sym, tv_interval="60")
        │      if page.url != url:
        │           await page.goto(url, wait_until="domcontentloaded")
        │           await page.wait_for_selector(CHART_READY, timeout=20_000)
        │      await dismiss_modals(page)
        │      png = await page.locator(MAIN_CHART_CANVAS).screenshot()
        │      path = _rotate_and_save_screenshot(png, sym)
        │      b64 = base64.b64encode(png).decode()
        └─ return {
             "type": "image", "data": b64,
             "mimeType": "image/png", "path": str(path),
             "symbol": sym, "timeframe": "1h",
             "warnings": [],
           }
```

### 6.2 Trace 2 — Phase 1 → Phase 2 closure

```
YOU: "Run iter 2 of the BTCUSDT strategy on TradingView's Strategy Tester."
      │
      ▼
[Tool]  tv_run_strategy_tester(slug="BTCUSDT-1h-iter2",
                               symbol="BTCUSDT", timeframe="1h")
        │
        ├─ async with page_lock() / throttle / require_login
        ├─ async with debug_on_failure(page, "tv_run_strategy_tester"):
        │
        │   1. Load Pine source from Phase 1 storage
        │      pine_path = ~/.tradingview_mcp_data/strategies/BTCUSDT-1h-iter2/strategy.pine
        │      code = pine_path.read_text()                # FileNotFoundError if absent
        │      issues = codegen.validate_pine(code)
        │      if any(i.severity == "error" for i in issues):
        │          raise ValueError(f"Pine validation failed: {issues}")
        │
        │   2. Open chart at requested symbol/timeframe
        │      sym = symbols.normalize("BTCUSDT")          # "BINANCE:BTCUSDT"
        │      await page.goto(CHART_URL_TPL.format(symbol=sym, tv_interval="60"))
        │      await page.wait_for_selector(CHART_READY)
        │      await dismiss_modals(page)
        │
        │   3. Open Pine Editor + set Monaco value
        │      await page.click(PINE_EDITOR_TAB)
        │      await page.wait_for_selector(PINE_EDITOR_READY)
        │      await _set_monaco_value(page, code)
        │
        │   4. Compile check BEFORE save
        │      err = await _pine_compile_error(page)
        │      if err:
        │          raise TVPineCompileError(err)
        │
        │   5. Save + Add to Chart
        │      await page.click(PINE_EDITOR_SAVE_BTN)
        │      await page.fill(SAVE_DIALOG_NAME_INPUT, f"yt_strategy_{slug}")
        │      await page.click(SAVE_DIALOG_CONFIRM_BTN)
        │      await page.click(PINE_EDITOR_ADD_TO_CHART_BTN)
        │
        │   6. Open Strategy Tester panel
        │      await page.click(STRATEGY_TESTER_TAB)
        │      await page.wait_for_selector(STRATEGY_TESTER_STATS_PANEL)
        │
        │   7. Extract stats via DOM scrape + screenshot
        │      stats = await _read_strategy_tester_stats(page)
        │      png = await page.locator(STRATEGY_TESTER_REPORT_REGION).screenshot()
        │      path = _rotate_and_save_screenshot(png, slug)
        │
        └─ return {
             "slug": slug, "symbol": sym, "timeframe": "1h",
             "stats": {
                "net_profit_pct": stats["net_profit_pct"],
                "max_drawdown_pct": stats["max_drawdown_pct"],
                "n_trades": stats["n_trades"],
                "win_rate_pct": stats["win_rate_pct"],
                "profit_factor": stats["profit_factor"],
                "sharpe": stats.get("sharpe"),
             },
             "screenshot_path": str(path),
             "screenshot_b64": base64.b64encode(png).decode(),
             "tv_pine_name": f"yt_strategy_{slug}",
             "warnings": [],
           }
```

### 6.3 Invariants across all flows

- **One mutex, one page.** Every tool body sits inside `async with page_lock()`.
- **Login + throttle + modal-dismiss before any meaningful work**, in that order.
- **Selectors only appear in `selectors.py`.** Any tool referencing a string selector inline is a CI lint reject.
- **Failures dump artifacts.** `debug_on_failure` runs on every tool except `tv_login_status` and `tv_close_browser` (which can't write debug if no page).
- **Screenshots return base64 + path, never raw bytes.** MCP-correct shape.
- **Symbol normalization happens once at tool entry**, then the normalized form is used everywhere.
- **`warnings: list[str]` on every success result.** Same semantics as Phase 1: non-fatal observations only.

---

## 7. Error handling

All tools return the existing `core/errors.py` envelope. Errors split into five categories. The assistant branches on `error_type="tv_browser"` and the specific `code`.

### 7.1 New `ErrorCode` values

| Code | Trigger | Retryable | Hint |
|---|---|---|---|
| `TV_NOT_LOGGED_IN` | `require_login` failed | true | Call `tv_open_login_prompt()` |
| `TV_LOGIN_TIMEOUT` | 5-min poll elapsed without login | true | Call `tv_open_login_prompt()` again |
| `TV_BROWSER_DEAD` | Chromium crashed + 2 relaunch failures | false | Inspect `debug_artifacts_path`; may need to delete `~/.tradingview_mcp_data/browser/` |
| `TV_SELECTOR_NOT_FOUND` | Documented selector returned no element | false | TV may have redesigned; check `selectors.py` and the debug screenshot |
| `TV_CLICK_INTERCEPTED` | Element existed but click was blocked (after one re-dismiss attempt) | true | Likely an undocumented modal is open; manual intervention may be needed |
| `TV_NAVIGATION_FAILED` | `page.goto()` raised after 3 retries | true | Check network or TV status |
| `TV_PINE_COMPILE_ERROR` | TV's Pine compiler returned an error after paste | true | Fix code and retry — strategy was NOT saved |
| `TV_LIMIT_REACHED` | TV refused due to plan ceiling (e.g. max alerts) | false | Delete an existing alert/indicator first |
| `TV_SUBSCRIPTION_REQUIRED` | Premium-only feature attempted on Free | false | Feature requires a paid TV plan |
| `TV_RATE_LIMITED` | TV-side 429 or rate banner | true | Wait the indicated interval and retry |
| `TV_CAPTCHA_CHALLENGE` | Cloudflare/bot-detection challenge | true | Solve the captcha in the visible browser, then retry |
| `TV_DOM_SHAPE_CHANGED` | Scraper found panel but couldn't extract fields | false | TV may have redesigned the panel; check `data.py` extraction logic |
| `TV_UNEXPECTED_STATE` | Catch-all: state we didn't anticipate | false | Inspect debug artifacts |

Plus the existing `INVALID_PARAMETER`, `INTERNAL_ERROR`, `DEPENDENCY_MISSING` codes apply where appropriate.

### 7.2 `make_tv_browser_error` helper

Added to `core/errors.py`:

```python
def make_tv_browser_error(
    code: ErrorCode | str,
    message: str,
    tool: str | None = None,
    debug_artifacts_path: str | None = None,
    retryable: bool = False,
    hint: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Construct a tv_browser-error envelope with `error_type="tv_browser"`."""
```

Fills in a default hint per code if `hint` is None, mirroring Phase 1's `make_strategy_error` pattern.

### 7.3 Wrapper translation matrix

| Caught exception | → Envelope code |
|---|---|
| `TVSessionExpired` | `TV_NOT_LOGGED_IN` |
| `TVLoginTimeout` | `TV_LOGIN_TIMEOUT` |
| `TVBrowserDead` | `TV_BROWSER_DEAD` |
| `playwright.TimeoutError` (selector wait) | `TV_SELECTOR_NOT_FOUND` |
| `playwright.Error` containing "intercepts pointer events" | `TV_CLICK_INTERCEPTED` (auto-retries dismiss_modals once first) |
| `playwright.Error` containing "ERR_NETWORK"/"ERR_TIMED_OUT"/"ERR_DNS" | `TV_NAVIGATION_FAILED` (after 3 retries) |
| `TVPineCompileError` | `TV_PINE_COMPILE_ERROR` |
| `TVRateLimit` | `TV_RATE_LIMITED` |
| `TVCaptchaChallenge` | `TV_CAPTCHA_CHALLENGE` |
| `TVDOMShapeChanged` | `TV_DOM_SHAPE_CHANGED` |
| `TVSubscriptionRequired` | `TV_SUBSCRIPTION_REQUIRED` |
| `TVLimitReached` | `TV_LIMIT_REACHED` |
| `ValueError` | `INVALID_PARAMETER` |
| `playwright.Error` (any other base-class subtype) | `TV_UNEXPECTED_STATE` |
| Anything else | `INTERNAL_ERROR` |

The wrapper catches `playwright.async_api.Error` (the base class), not just `TimeoutError`. Novel playwright error subtypes are downcast or fall through to `TV_UNEXPECTED_STATE`.

### 7.4 Envelope examples

`TV_SELECTOR_NOT_FOUND`:

```json
{
  "error": {
    "code": "TV_SELECTOR_NOT_FOUND",
    "error_type": "tv_browser",
    "tool": "tv_paste_pine",
    "message": "Selector 'PINE_EDITOR_SAVE_BTN' did not appear within 10s.",
    "selector_name": "PINE_EDITOR_SAVE_BTN",
    "selector_value": "button[data-name=\"save\"]",
    "hint": "TradingView may have changed the Pine Editor DOM. Check tv_browser/selectors.py and the debug screenshot.",
    "debug_artifacts_path": "/Users/.../browser_debug/2026-06-04T12-34-56-tv_paste_pine/",
    "retryable": false
  }
}
```

`TV_PINE_COMPILE_ERROR`:

```json
{
  "error": {
    "code": "TV_PINE_COMPILE_ERROR",
    "error_type": "tv_browser",
    "tool": "tv_paste_pine",
    "message": "Pine compile error: line 12: syntax error at 'inpt.int'",
    "pine_error_text": "<verbatim multi-line panel content>",
    "line": 12,
    "hint": "Fix the typo and call tv_paste_pine again. The strategy was NOT saved.",
    "retryable": true
  }
}
```

`TV_CAPTCHA_CHALLENGE`:

```json
{
  "error": {
    "code": "TV_CAPTCHA_CHALLENGE",
    "error_type": "tv_browser",
    "tool": "tv_open_chart",
    "message": "Cloudflare/TradingView bot-detection challenge encountered.",
    "hint": "A visible captcha is on screen. Solve it in the open browser, then retry the tool.",
    "debug_artifacts_path": "...",
    "retryable": true
  }
}
```

### 7.5 Principles applied

- **Every authed tool wraps in `debug_on_failure`.** Every error envelope has a `debug_artifacts_path` field (may be empty for `tv_login_status` etc.).
- **No retries inside tool bodies for assistant-driven errors.** Pine compile, limit reached, login required → surface; do not loop.
- **Auto-retries for transient infrastructure only.** Navigation retried 3× silently; browser-dead relaunch retried 1×; click-intercepted re-dismissed 1×.
- **`retryable: bool` is advisory.** Tells the assistant whether re-calling with same args is sensible.
- **Failed Pine paste leaves no garbage on TV.** Compile check runs before save click — verified in §6 data flow.
- **No raw playwright stack traces leak.** All errors translated through the wrapper; tracebacks go to stderr only.
- **`warnings: list[str]` is only ever used on success.** Never inside an error envelope.

---

## 8. Testing strategy

Three test layers + manual checklist. Unit-test everything with mocked playwright; integration-test the critical paths against a local fake TV server; smoke-test against real TV on demand.

### 8.1 Unit tests — `tests/unit/tv_browser/`

Mocked `playwright.async_api.Page` via `AsyncMock`. All tests are `@pytest.mark.asyncio`-marked.

| Module | What we test | Mocking |
|---|---|---|
| `browser.py` | Singleton; auto-relaunch on dead context (once); idle timer fires after timeout; idle defers while lock held; idle disabled during interactive_login | Mock `playwright.async_api.async_playwright` + freezegun |
| `session.py` | `is_logged_in` navigates to `_TV_BASE` if elsewhere; `require_login` raises `TVSessionExpired`; `interactive_login` polls and times out; `logout` removes `user_data_dir` | Mock page; `monkeypatch.setenv("TV_BROWSER_USER_DATA_DIR", ...)` + `tmp_path` |
| `modals.py` | Tries every selector in `MODAL_DISMISS_SELECTORS`; returns dismissal count; idempotent | Mock page.locator |
| `throttle.py` | Two rapid calls space by min interval; concurrent callers serialize | Real asyncio sleeps |
| `symbols.py` | All routing cases including aliases and unknowns; parametrized | None (pure function) |
| `chart`, `data`, `pine`, `alerts`, `watchlists` | Correct selector references; correct call sequence; normalization called once at entry; warnings propagated | Mock page; assert call args |
| `debug.py` | Artifacts written on exception; rotation deletes oldest beyond max-N | tmp_path + frozen time |
| `selectors.py` | URL templates resolve correctly when `TV_BASE_URL` is set | `monkeypatch.setenv` |
| Error envelopes | Each new `ErrorCode` constructs the right envelope via `make_tv_browser_error` | Static |

Coverage target: **80% on new modules**, **100% on `browser.py` lifecycle paths** (mutex, relaunch, idle, shutdown). `pytest-cov` enforces.

### 8.2 Selector pinning — `tests/unit/tv_browser/test_selectors_pinned.py`

A SEPARATE `EXPECTED_SELECTORS` dict in the test file. Catches "edited `selectors.py` without updating the test baseline" (and vice versa) — two-keys-in-two-pockets.

```python
EXPECTED_SELECTORS = {
    "CHART_READY":            '[data-name="legend-source-item"]',
    "PINE_EDITOR_SAVE_BTN":   'button[data-name="save"]',
    "LOGGED_IN_INDICATOR":    'button[aria-label="Open user menu"]',
    # …every selector pinned…
}

@pytest.mark.parametrize("name,expected", EXPECTED_SELECTORS.items())
def test_selector_pinned(name, expected):
    actual = getattr(selectors, name)
    assert actual == expected, (
        f"Selector {name} changed. If TV redesigned, update both selectors.py "
        f"AND EXPECTED_SELECTORS in the same commit."
    )
```

### 8.3 Wrapper-enforcement test — `tests/unit/tv_browser/test_wrapper_invariants.py`

Runtime test (not AST): monkeypatch `page.locator` to raise on every call, then invoke each of the 17 MCP tool functions. For each, assert that artifacts were written to `~/.tradingview_mcp_data/browser_debug/<ts>-<tool>/`. Any tool whose body bypassed `debug_on_failure` produces no artifact and the test fails for *that specific tool*.

### 8.4 Integration tests — `tests/integration/tv_browser/`

A locally-served fake TV server. Tests run real playwright against `http://127.0.0.1:<port>/`.

```
tests/fixtures/fake_tv/
├── server.py                # aiohttp app, picks random free port
├── pages/
│   ├── chart.html           # canvas + CHART_READY anchor + ticker search
│   ├── pine_editor.html     # real Monaco from CDN + save/add-to-chart
│   ├── strategy_tester.html # stats panel with parseable rows
│   ├── alerts.html          # alert list + create dialog (price-cross only)
│   ├── watchlist.html       # symbol rows + watchlist dropdown
│   └── login.html           # simulates tradingview.com/signin
```

Server lifecycle: session-scoped pytest fixture starts aiohttp on a random free port, sets `TV_BASE_URL` env, yields, shuts down at session end. Browser context is session-scoped; each test gets a fresh page (new tab) for isolation.

Pine Editor fixture includes a **real Monaco instance from a CDN** so `_set_monaco_value` is exercised against actual Monaco's `setValue` API, not a stub.

Coverage:
- Happy paths for all 17 tools.
- DOM-shape-changed variants (rendered pages with intentionally broken structure → assert `TV_SELECTOR_NOT_FOUND` / `TV_DOM_SHAPE_CHANGED`).
- First-ever-login flow against `login.html` — simulate user click sequence; verify `is_logged_in` flips and `interactive_login` returns.

Race-condition tests use a pattern like:

```python
async def test_idle_timer_defers_while_lock_held():
    started, finished = asyncio.Event(), asyncio.Event()
    async def hold_lock():
        async with page_lock() as page:
            started.set()
            await finished.wait()
    task = asyncio.create_task(hold_lock())
    await started.wait()
    fired = await _fire_idle_timer_once()   # internal test hook
    assert fired is False
    finished.set()
    await task
```

### 8.5 E2E smoke — `tests/e2e/tv_browser/`

Off-CI. Manual / on-demand against real TV with a test profile.

```python
@pytest.mark.skipif(not os.environ.get("TV_E2E"), reason="requires TV_E2E=1 + live login")
async def test_real_tv_screenshot_btc_chart():
    result = await tv_screenshot_chart("BTCUSDT", "1h")
    assert result["mimeType"] == "image/png"
    assert len(result["data"]) > 10_000
```

Run: `TV_E2E=1 uv run pytest tests/e2e -v`. Used after TV redesigns or before tagging a release. Never in CI.

### 8.6 Manual checklist — `docs/tv_browser_manual_check.md`

Numbered list of the 17 tools to walk through against real TV after any selector patch. Each item: "Open Claude Desktop, ask for X; verify Y; time ≤ 5 s." Takes ~20 min end-to-end.

### 8.7 What we explicitly don't test
- TV's own correctness (Strategy Tester math, alert delivery).
- Claude's visual interpretation of screenshots.
- Cross-browser (pinned to Chromium).
- Selector resilience to all TV redesigns (that's what 8.2 + 8.6 + manual triage are for).

### 8.8 CI integration

Extend `.github/workflows/test.yml`:
- Job `unit-tv` — unit + selector-pinning + wrapper-invariants (fast, <1 min).
- Job `integration-fake-tv` — fake-TV integration (~3 min). Includes `playwright install chromium` step.
- E2E gated by `TV_E2E=1`, never in CI.
- Run pytest with `--video=retain-on-failure --tracing=retain-on-failure` (pytest-playwright plugin) so failed integration tests automatically save traces.

### 8.9 Discipline
- Every selector reference outside `selectors.py` is a CI lint failure (regex-grep step).
- Every tool body wraps in `debug_on_failure` is enforced by the test in §8.3.
- Flakiness policy: strict pass/fail. No `pytest-rerunfailures`. If a test flakes, root-cause and fix.
- Test isolation: session-scoped browser, function-scoped page (new tab per test).
- Fake TV fixture sync: refresh `fake_tv/pages/*.html` after major selector patches; quarterly review otherwise. Documented in `tests/fixtures/fake_tv/README.md`.

### 8.10 New dev dependencies for testing
- `pytest-asyncio>=0.23`
- `pytest-cov>=4.1`
- `pytest-playwright>=0.5` (provides `--video`, `--tracing` CLI flags)
- `aiohttp>=3.9` (for fake TV server)
- `freezegun>=1.4` (for idle-timer tests)

---

## 9. New runtime dependencies

To be added to `pyproject.toml` `[project] dependencies`:

| Package | Why |
|---|---|
| `playwright>=1.40` | Browser automation core |

Plus a post-install step: `playwright install chromium`. Documented in `INSTALLATION.md` and run automatically in the CI workflow.

---

## 10. Configuration / env vars

Documented in `.env.example`.

### 10.1 New env vars

| Var | Default | Purpose |
|---|---|---|
| `TV_BASE_URL` | `https://www.tradingview.com` | Base URL for all TV pages (overridden by integration tests) |
| `TV_BROWSER_USER_DATA_DIR` | `~/.tradingview_mcp_data/browser` | Persistent Chromium profile directory |
| `TV_BROWSER_HEADLESS` | `false` | Whether the browser window is visible. Set `true` for batch usage |
| `TV_BROWSER_IDLE_S` | `300` | Idle seconds before the browser auto-shuts-down |
| `TV_BROWSER_MIN_INTERVAL_MS` | `500` | Min wall-clock between any two browser actions |
| `TV_BROWSER_DEBUG_TRACES` | `false` | If true, also capture playwright traces in debug artifacts |
| `TV_BROWSER_DEBUG_MAX` | `20` | Max debug artifact folders kept under `browser_debug/` |
| `TV_E2E` | unset | Gate for `tests/e2e/` execution |

### 10.2 No new secrets required.

### 10.3 Caveats
- **SIGTERM cleanup:** if Claude Desktop kills the MCP server hard, async cleanup may not finish; trace files could be left half-written. Not a correctness issue (TV state is unaffected), just diagnostic-data loss.
- **macOS GateKeeper:** first launch of playwright's Chromium binary may prompt for permission. Documented in `INSTALLATION.md`.

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| TV redesigns break selectors | Selectors centralized in `selectors.py`; selector-pinning tests force conscious updates; debug artifacts include selector name + value so triage is fast (2–4 patches/year expected). |
| Cloudflare bot detection flags the account | Conservative throttle (`TV_BROWSER_MIN_INTERVAL_MS=500`); headed by default looks more human-like; `TV_CAPTCHA_CHALLENGE` surfaces the challenge cleanly for manual solve. |
| TV session expires mid-session | `require_login` runs at every tool entry; `TV_NOT_LOGGED_IN` surfaces immediately with a clear "call tv_open_login_prompt" hint. |
| LLM-generated Pine doesn't compile in TV | `_pine_compile_error` runs before any save; failed compile raises `TV_PINE_COMPILE_ERROR` with full panel text and line number; no garbage written to TV. |
| Browser process leaks file descriptors over long sessions | 5-min idle auto-close releases resources; `tv_close_browser` available for manual reset. |
| Persistent profile corruption | `TV_BROWSER_DEAD` error includes hint to delete `user_data_dir`; `tv_logout()` provides the same via `shutil.rmtree`. |
| Race between idle timer and active tool | Idle timer task `await`s on lock-not-held and the `disable_idle` flag; tested in §8.4 with deterministic event-based race tests. |
| Monaco editor changes API | `_set_monaco_value` is one helper in one file; integration test against real Monaco from CDN catches API regressions before merge. |
| TV updates the alert dialog structure | Alert MVP scope deliberately narrow (price-cross only) — smaller surface to maintain; full alert builder deferred. |
| User's normal Chrome and our Chromium collide | They don't — playwright launches a separate Chromium binary with its own profile. Worst case: two TV-logged-in windows on screen. |
| Cookies expire after ~30 days | `TV_NOT_LOGGED_IN` fires cleanly; assistant calls `tv_open_login_prompt`; user logs in once and resumes. |
| MCP client calls two tv tools concurrently | Page lock serializes; throttle ensures pacing. |

---

## 12. Open questions

None outstanding at design close. Implementation may surface decisions worth a quick check-in (e.g., exact strategy-tester stat field names if TV's labeling differs from what we assumed) — those go through the implementation plan, not back to design.

---

## 13. Out-of-MVP follow-ups (Phase 2.5 / Phase 3)

- Full alert builder (column / operator / value with all TV's options) — deferred.
- Pine v6 indicator add for premium-locked indicators (currently surfaces `TV_SUBSCRIPTION_REQUIRED`).
- Watchlist *creation* and *deletion* (current scope: add/remove symbols to existing).
- Multi-account profile switching (currently: `tv_logout()` clears, log in to next).
- Headless screenshot fast-path (`TV_BROWSER_HEADLESS=true` works today; not optimized).
- Browser-CDP attach to user's existing Chrome (alternative to launching our own Chromium).
- Phase 3 standalone Pine generator MCP — separate spec when ready.
- Live trading / broker connect — explicitly out of project scope.
