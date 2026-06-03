# YT → Backtest MCP Tool — Design Spec

**Date:** 2026-06-03
**Status:** Approved for implementation planning
**Sub-project:** 1 of 3 (Phase 1)
**Owner:** Andrew Fackrell
**Parent project:** Trading-MCP / tradingview-mcp

---

## 1. Goal

Add three MCP tools to the existing `tradingview-mcp` server that, together, let Claude Desktop turn a YouTube video describing a trading strategy into a working, walk-forward-validated backtest plus a TradingView Pine v6 script — with deterministic parameter auto-tuning when needed.

End-state user flow:

> User: *"Backtest the strategy in this YouTube video for BTC-USDT on the 1h timeframe."*
>
> Claude Desktop: *"Strategy converged on iter 2. IS Sharpe 1.5, OOS Sharpe 1.3 (no overfit). Beats buy-and-hold by +18% over 2 years. Files saved at `~/.tradingview_mcp_data/strategies/BTC-USDT-1h-iter2/`: `strategy.py`, `strategy.pine`, `report.json`, `equity_curve.png`."*

This spec covers Phase 1 only. Browser-driven TradingView UI access (Phase 2) and standalone Pine generator (Phase 3) are separate sub-projects with their own future specs.

---

## 2. Non-goals

- Multi-asset / pairs / basket strategies — `backtesting.py` is single-symbol native. Future Phase 3+ with `vectorbt` if needed.
- Strategies that consume non-OHLCV inputs (sentiment, on-chain, funding rates, fundamentals). Transcript extractor flags dropped rules; tool does not implement them.
- Live trading / order execution.
- TradingView account integration (Pine still requires manual paste into TV's Pine Editor).
- Pine syntax-correctness *execution* check — we validate structure only; runtime correctness requires TV.
- LLM behavioral quality (i.e., this spec does not test "does Claude write good strategies"). The tool is an instrument the LLM uses; instrument quality is testable, instrument-user quality is not.

---

## 3. Locked design decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Iterative auto-tune** loop (generate → backtest → evaluate → adjust → retry) | User-selected workflow shape. |
| 2 | **`backtesting.py`** as the backtest framework | LLM-friendly OOP API (`class MyStrategy(Strategy)`), built-in metrics + trade log + equity curve, native `Backtest.optimize()`, single-asset constraint accepted. |
| 3 | **MCP tools added to existing `tradingview-mcp`** server | Reuses Claude Desktop wiring already installed; visible in tool menu; no new MCP server. |
| 4 | **Yahoo Finance + Binance public klines** as the data backbone | Yahoo for stocks/ETFs/FX/indices; Binance for full-history crypto intraday. Both unauthenticated. |
| 5 | **Always emit both Python + Pine v6** | Closes the loop with TradingView. Generated once per converged final strategy, not per iteration. |
| 6 | **Stop on `max_iters` reached OR Sharpe ≥ target`** | Predictable cost; assistant-overridable defaults. |
| 7 | **Approach C — Hybrid architecture** (thin MCP primitives + deterministic auto-tune helper) | Assistant orchestrates strategy *structure* changes (observable in chat); server-side helper does *parameter* sweeps deterministically (cheap, no LLM tokens). |

---

## 4. Architecture

Three MCP tools added to `tradingview-mcp`. New code lives under `src/tradingview_mcp/core/services/yt_strategy/` so existing services stay untouched.

```
┌────────────────────────────────────────────────────────────────┐
│  Claude Desktop (user + assistant)                             │
│   "Backtest the strategy in this YT video for BTC-USDT on 1h"  │
└────────────────────────┬───────────────────────────────────────┘
                         │ (MCP over stdio)
        ┌────────────────┴────────────────┬───────────────────────┐
        ▼                                 ▼                       ▼
┌──────────────────┐         ┌────────────────────────┐  ┌──────────────────┐
│ yt_extract_      │         │ run_strategy_backtest  │  │ auto_tune_       │
│ strategy(url)    │         │ (code, symbol, tf, …)  │  │ strategy(code,…) │
│                  │         │                        │  │                  │
│ - yt-dlp / API   │         │ - Fetch OHLCV          │  │ - skopt /        │
│ - transcript     │         │ - exec strategy class  │  │   grid search    │
│ - rule stub      │         │ - backtesting.py run   │  │ - returns best   │
│ - python skel.   │         │ - walk-forward OOS     │  │   params + trials│
│ - pine skel.     │         │ - B&H benchmark        │  │ - heatmap PNG    │
└──────────────────┘         │ - persist run dir      │  └──────────────────┘
                             └────────────────────────┘
                                          │
                                          ▼
                               Yahoo Finance  /  Binance klines
                                          │
                                          ▼
                  ~/.tradingview_mcp_data/strategies/<slug>/
                          ├── strategy.py
                          ├── strategy.pine
                          ├── report.json
                          ├── equity_curve.png
                          └── transcript.txt
```

The assistant in Claude Desktop drives the loop:

1. `yt_extract_strategy(url)` → transcript + skeleton.
2. Assistant fills in skeleton → real `strategy_code` + `pine_code`.
3. `run_strategy_backtest(strategy_code, symbol, ...)` → metrics including OOS + B&H benchmark.
4. If OOS Sharpe < target and iters < max:
   - If parameter-tune likely sufficient → `auto_tune_strategy(...)` then loop to step 3 with patched code.
   - Else → assistant revises strategy structure, loop to step 3.
5. On convergence → final artifacts persisted; report returned.

---

## 5. Components

Each module has one clear purpose, communicates through a defined interface, can be tested independently. All under `src/tradingview_mcp/core/services/yt_strategy/`.

### 5.1 `transcript.py`
**Purpose:** YouTube URL → plaintext transcript + video metadata.

```python
def fetch_transcript(url: str) -> TranscriptResult
# returns: {text, language, duration_s, title, channel, source}
```

Tries in order:
1. `youtube-transcript-api` (free, no auth, handles auto-captions).
2. `yt-dlp --write-auto-subs` as fallback for videos that block the API.

Caches by video ID under `~/.tradingview_mcp_data/transcripts/<video_id>.json` (24h TTL). No transcript available → raises `TranscriptUnavailable`.

### 5.2 `rule_extractor.py`
**Purpose:** Transcript → structured `StrategySpec` stub.

```python
def extract_rules(transcript: str) -> StrategySpec
```

MVP returns the raw transcript as a single rule. Actual rule extraction is delegated to the assistant in Claude Desktop reading the transcript. This keeps the server free of Anthropic API calls (Approach C contract).

`StrategySpec` fields: `name`, `entry_rules: list[str]`, `exit_rules: list[str]`, `indicators_used: list[str]`, `timeframe_hint: str | None`, `asset_hint: str | None`, `position_sizing: str | None`, `risk_management: str | None`, `confidence: float`.

### 5.3 `codegen.py`
**Purpose:** Provide template scaffolds the assistant fills in.

```python
def python_template(spec: StrategySpec) -> str   # backtesting.py Strategy skeleton
def pine_template(spec: StrategySpec) -> str     # Pine v6 strategy skeleton
def validate_pine(code: str) -> list[Issue]      # structural validation
```

Both templates share a single audited skeleton so Pine and Python versions don't drift.

`validate_pine` checks: `//@version=6` present, exactly one of `indicator()`/`strategy()`/`library()` call, brace/paren balance, no obviously invalid syntax. Cheap insurance; not a runtime check.

### 5.4 `data.py`
**Purpose:** Unified OHLCV fetch across Yahoo + Binance.

```python
def fetch_ohlcv(symbol: str, timeframe: str, period: str) -> pd.DataFrame
def cost_profile_for(symbol: str) -> CostProfile
```

Routes by symbol shape:

| Pattern | Source | Examples |
|---|---|---|
| Bare alphanumeric, ends with `USDT`/`BUSD`/`BTC`/`ETH` | Binance public `/api/v3/klines` (no auth) | `BTCUSDT`, `ETHBTC`, `SOLBUSD` |
| Anything else | Yahoo Finance via existing `yahoo_finance_service` | `AAPL`, `BTC-USD`, `^GSPC`, `EURUSD=X` |

Output is a `DataFrame` indexed by UTC datetime with cols `Open, High, Low, Close, Volume` — exact shape `backtesting.py` expects.

`cost_profile_for(symbol)` returns asset-class-aware defaults:

| Symbol pattern | Commission | Slippage | Note |
|---|---|---|---|
| Binance spot crypto | 0.10% | 0.05% | Maker-equivalent |
| Yahoo equity — any Yahoo symbol not matching the FX or crypto patterns below (`AAPL`, `^GSPC`, `TSLA`, `VOO.L`, etc.) | 0.00% | 0.02% | Retail broker (Alpaca/IBKR Lite baseline) |
| Yahoo FX — symbol ending `=X` (`EURUSD=X`) | 0.02% | 0.01% | Spread approximation |
| Yahoo crypto-as-USD — symbol ending `-USD` (`BTC-USD`) | 0.10% | 0.05% | Crypto defaults |

Profile is overridable via tool args. Profile name is printed in the report so it's visible.

Validates `timeframe` against per-source allow-list (`Binance: 1m,5m,15m,1h,4h,1d,1w`; `Yahoo: 1m intraday ≤7d, 5m/15m/30m/60m intraday ≤60d, 1d/1wk/1mo daily long history`) and clamps `period` if it exceeds source limits (warning emitted unless `strict_period=True`).

### 5.5 `runner.py` — security-critical
**Purpose:** Safely execute LLM-generated strategy code and return results.

```python
def run_backtest(
    strategy_code: str,
    symbol: str,
    timeframe: str,
    period: str,
    cash: float = 10_000,
    commission: float | None = None,   # default from cost_profile_for(symbol)
    slippage: float | None = None,
    oos_validate: bool = True,
) -> BacktestResult
```

**Defense-in-depth security model:**

1. **AST pre-scan** rejects code before exec when it references forbidden names:
   - Banned imports: `os`, `subprocess`, `socket`, `urllib`, `requests`, `httpx`, `aiohttp`, `ftplib`, `smtplib`, `shutil`, `glob`, `pickle`, `marshal`, `ctypes`, `multiprocessing`, `threading`.
   - Banned builtins: `open`, `eval`, `exec`, `compile`, `__import__`, `globals`, `locals`, `vars`, `breakpoint`.
   - Banned dunder reflection: `getattr(x, "__name__")` calls where the second arg is a string literal starting with `__`; same rule for `setattr`/`delattr`/`hasattr`.
   - Banned attribute access: any name access matching `__class__`, `__bases__`, `__subclasses__`, `__globals__`, `__builtins__`, `__mro__`, `__code__`, `__dict__` (the last is allowed only on `self.data`).
2. **Restricted exec namespace**: only `backtesting`, `pandas as pd`, `numpy as np`, `ta` (technical-analysis lib), `math`, `statistics` are in scope. Custom `__builtins__` containing only safe names.
3. **Subprocess isolation**: strategy code runs in a `multiprocessing.Process` (not the MCP server process). Uses `spawn` start method on macOS for clean isolation.
4. **Wall-clock timeout**: `process.join(timeout=60)` then `process.kill()`. Configurable via `RUNNER_TIMEOUT_S` env var (default 60).
5. **Memory cap**: `resource.setrlimit(RLIMIT_AS, 1_000_000_000)` inside subprocess (1 GB). Configurable via `RUNNER_MEMORY_MB`.
6. **No stdin/stdout to user code**: subprocess stdio is captured; whatever the strategy prints stays in the runner.

After successful exec, runner verifies a `Strategy` subclass is defined. Then:

- Fetches OHLCV via `data.fetch_ohlcv()`.
- If `oos_validate=True`: delegates to `walkforward.py` for expanding-window walk-forward analysis. Algorithm: data is divided into 6 equal-length chunks; for fold *k* ∈ {1..5}, train on chunks 1..*k* and test on chunk *k*+1. Yields 5 OOS test windows. OOS metrics are aggregated across folds (mean Sharpe, worst-fold drawdown, etc.); IS metrics are computed once on the full dataset for comparison. With `oos_validate=False`, a simple 70/30 chronological train-test split is run instead — never omitted entirely.
- Computes B&H benchmark over the same window via existing `backtest_service._buy_and_hold_return`.
- Generates equity-curve PNG via `Backtest.plot(open_browser=False)`.

Returns `BacktestResult`:

```python
{
  "in_sample":     {sharpe, cagr, mdd, win_rate, profit_factor, n_trades},
  "out_of_sample": {sharpe, cagr, mdd, win_rate, profit_factor, n_trades},
  "benchmark":     {bh_return_pct, bh_sharpe},
  "overfit_flag":  bool,                # True if OOS Sharpe < 0.5 * IS Sharpe
  "trade_log":     [...],
  "equity_curve_png_path": "...",
  "run_path":      "~/.tradingview_mcp_data/strategies/<slug>/",
  "slug":          "...",
  "cost_profile":  "binance_crypto_spot",
  "warnings":      [...]                # e.g. ["dropped rule: 'when funding rate negative'"]
}
```

### 5.6 `walkforward.py`
**Purpose:** Out-of-sample validation via rolling train/test windows.

```python
def walk_forward_split(
    data: pd.DataFrame,
    n_folds: int = 6,
    train_frac: float = 0.7,
    expanding: bool = True,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]
```

Returns list of `(train_df, test_df)` pairs using the algorithm described in §5.5 (5 folds from 6 chunks, expanding). Caller backtests on each pair, aggregates OOS metrics across folds.

Overfit flag fires when aggregated OOS Sharpe < 50% of IS Sharpe. Logic mirrors the existing `walk_forward_backtest` in `backtest_service.py:583` for consistency with the project's existing patterns.

### 5.7 `autotune.py`
**Purpose:** Deterministic parameter optimization. No LLM.

```python
def auto_tune(
    strategy_code: str,
    param_grid: dict[str, list],
    symbol: str, timeframe: str, period: str,
    metric: str = "Sharpe Ratio",
    method: str = "grid",          # "grid" | "skopt"
    max_tries: int = 50,
    seed: int = 42,
) -> AutoTuneResult
```

Uses `backtesting.py`'s `Backtest.optimize()` which wraps grid search and scikit-optimize. Seed pinned for reproducibility.

Returns:

```python
{
  "best_params":   {...},
  "best_metric":   1.42,
  "metric_name":   "Sharpe Ratio",
  "heatmap_png_path": "...",     # for 2-param grids only
  "all_trials":    [...]         # list of {params, metric}, sorted desc
}
```

### 5.8 `storage.py`
**Purpose:** Persist runs under a slug-keyed dir.

```python
def save_run(slug: str, artifacts: RunArtifacts) -> Path
def load_run(slug: str) -> RunArtifacts
def list_runs() -> list[RunSummary]
```

Layout under `~/.tradingview_mcp_data/strategies/<slug>/`:

```
strategy.py
strategy.pine
report.json
equity_curve.png
transcript.txt
```

Slug format: `{video_id}-{symbol}-{timeframe}-iter{n}` (e.g., `dQw4w9WgXcQ-BTCUSDT-1h-iter2`). Auto-tune iterations do *not* persist; only `run_strategy_backtest` calls write to disk. Keeps history clean and re-runnable.

### 5.9 `server.py` additions
Three new MCP tool registrations in `src/tradingview_mcp/server.py`:

1. `yt_extract_strategy(url: str) -> dict`
2. `run_strategy_backtest(strategy_code, symbol, timeframe, period, cash?, commission?, slippage?, oos_validate?, slug?) -> dict`
3. `auto_tune_strategy(strategy_code, param_grid, symbol, timeframe, period, metric?, method?, max_tries?) -> dict`

Each is a thin wrapper: validates inputs against the existing `core/utils/validators.py` patterns, calls the relevant module, returns a JSON-serializable result. Errors use the existing `core/errors.py` envelope.

---

## 6. Data flow — full convergence cycle

```
USER:  "Backtest the strategy from <youtube URL> for BTC-USDT on 1h, target sharpe 1.2"
       │
       │ Assistant decides to call yt_extract_strategy
       ▼
[Tool 1] yt_extract_strategy(url)
   ├─ transcript.fetch_transcript(url)
   ├─ cache check (~/.tradingview_mcp_data/transcripts/)
   ├─ codegen.python_template(spec_stub)
   ├─ codegen.pine_template(spec_stub)
   └─ returns: {transcript, video_meta, python_skeleton, pine_skeleton}
       │
       │ Assistant reads transcript, fills in skeleton →
       │ produces real strategy_code (Python) + pine_code
       ▼
[Tool 2] run_strategy_backtest(strategy_code, symbol="BTCUSDT", timeframe="1h",
                              period="2y", oos_validate=True, slug="iter1")
   ├─ data.fetch_ohlcv()                          ← Binance for BTCUSDT
   ├─ data.cost_profile_for("BTCUSDT")            ← binance_crypto_spot (0.10%)
   ├─ AST pre-scan of strategy_code               ← reject forbidden names
   ├─ launch subprocess (60s timeout, 1GB cap)
   │     └─ backtesting.py runs strategy
   ├─ walkforward.walk_forward_split (6 folds, 70/30)
   ├─ buy-and-hold benchmark on same window
   ├─ storage.save_run("BTCUSDT-1h-iter1", {...})
   └─ returns: BacktestResult{in_sample, out_of_sample, benchmark, overfit_flag, ...}
       │
       │ Assistant inspects: OOS sharpe=0.6 < target 1.2 → not done
       │ Decides: parameter space looks fine, just tune
       ▼
[Tool 3] auto_tune_strategy(strategy_code,
            param_grid={"rsi_period":[10,14,21,28], "oversold":[20,25,30]},
            symbol, timeframe, period, metric="Sharpe Ratio",
            method="skopt", max_tries=30)
   ├─ backtesting.py Backtest.optimize(..., random_state=42)
   ├─ pure compute, no LLM
   └─ returns: {best_params, best_metric, heatmap_png_path, all_trials}
       │
       │ Assistant patches the code with best params, slug="iter2"
       ▼
[Tool 2 again] run_strategy_backtest(patched_code, ..., slug="iter2")
       │
       │ OOS sharpe=1.3 ≥ target → done
       ▼
ASSISTANT TO USER:
   "Strategy converged on iter 2.
    IS sharpe 1.5, OOS sharpe 1.3 (no overfit), beats B&H by +18% over 2y.
    Files saved: ~/.tradingview_mcp_data/strategies/BTCUSDT-1h-iter2/"
```

### Data-flow invariants

- **Every Tool 2 call writes a full run dir.** Auto-tune iterations don't pollute storage; only `run_strategy_backtest` persists.
- **OOS metrics are non-negotiable.** Even if `oos_validate=False` is passed, a basic train-test split is run and reported — never omitted.
- **The assistant never sees raw `exec()` errors.** `runner.py` catches them, structures them into the `core/errors.py` envelope, returns a clean error object.
- **Pine output is generated only for the final converged strategy**, not per iteration. Saves cycles; the assistant translates only the winning Python into Pine after the loop exits.

---

## 7. Error handling

All MCP tools return the structured envelope from existing `core/errors.py`. Errors split into four categories; the assistant branches on `error_type`.

### 7.1 Input errors (`error_type="input"`)
Caught at tool entry before any work. Recoverable by the assistant fixing arguments.

| Trigger | Returned message |
|---|---|
| Invalid YT URL | `"Not a valid YouTube URL"` + accepted formats |
| Unknown symbol | `"Symbol 'XYZ' not found on Yahoo or Binance"` + suggestion list |
| Invalid timeframe for source | `"Binance does not support timeframe '8h'; valid: 1m,5m,15m,1h,4h,1d"` |
| Period exceeds source limit | Auto-clamp + warning (default) or hard-fail (`strict_period=True`) |

### 7.2 Data errors (`error_type="upstream"`)
Reuses the transient-retry pattern from existing `screener_provider.py:115` (`_is_transient_screener_error`). Retries 3× with `[0.5, 1.5, 4.0]s` backoff before surfacing.

| Trigger | Behavior |
|---|---|
| Yahoo rate limit / 429 / connection reset | Retry with backoff |
| Binance connection reset / 5xx | Retry with backoff |
| YT transcript 404 (no captions) | No retry → suggest manual `transcript_override` (future param) |
| Empty OHLCV (delisted) | No retry → suggest checking listing date |

### 7.3 Strategy code errors (`error_type="strategy"`)
LLM-generated code fault. Richly structured so the assistant can fix it in the next turn:

```json
{
  "error_type": "strategy",
  "error_class": "ImportError" | "AttributeError" | "Timeout" | "SecurityViolation" | "RuntimeError" | "AssertionError" | "NoTrades" | "MemoryExceeded" | "InvalidStrategyClass",
  "message": "name 'tslib' is not defined",
  "user_code_line": 23,
  "user_code_snippet": "    sma = tslib.SMA(self.data.Close, 20)",
  "hint": "Only 'backtesting', 'pandas', 'numpy', 'ta' are available. Use ta.trend.SMAIndicator or numpy.convolve."
}
```

`user_code_line` and `user_code_snippet` are `null` for `Timeout`, `MemoryExceeded`, and `InvalidStrategyClass` subtypes (no specific line is at fault). For `SecurityViolation`, both are populated with the location of the offending AST node.

Subtypes and hints:

| Subtype | Trigger | Hint |
|---|---|---|
| `SecurityViolation` | AST scan rejects forbidden name | Lists offending name + allow-list of available names |
| `Timeout` | Subprocess > 60s | `"Strategy did not converge within 60s. Check for infinite loops or O(n²) logic over bar history."` |
| `MemoryExceeded` | RLIMIT_AS hit | `"Strategy used > 1GB. Avoid per-bar arrays; use self.data slicing."` |
| `NoTrades` | `n_trades == 0` | `"Strategy produced 0 trades. Entry/exit conditions may never both fire. Check signal logic."` |
| `InvalidStrategyClass` | exec OK but no `Strategy` subclass found | `"Code must define a class subclassing backtesting.Strategy."` |
| `ImportError`/`AttributeError`/`RuntimeError` | Runtime failure inside strategy | Pass through with line + snippet + hint |

### 7.4 Server errors (`error_type="server"`)
Anything not caught above. Full traceback to stderr (visible in Claude Desktop's MCP logs). Generic message to user (`"Internal error; see MCP server logs"`). Stack traces never leak through the MCP envelope.

### 7.5 Principles applied across the stack
- **Fail loud, recover quietly.** Transient stuff retries silently; deterministic stuff fails with a specific actionable suggestion.
- **One way to fail per call.** Tools return either a full result or a structured error — never partial-result-with-embedded-error. Exception: `warnings: list[str]` for non-fatal flags ("dropped fundamental rule").
- **All errors JSON-serializable.** No Python objects, exception instances, or file handles in the envelope.
- **Strategy errors include enough for retry.** Line numbers + snippets + hints. Approach C's auto-tune loop only works if the assistant can debug previous iterations from the error response alone.

---

## 8. Testing strategy

Three test layers, mirrored at module boundaries. Repo already uses pytest.

### 8.1 Unit tests — `tests/unit/yt_strategy/`

| Module | What we test | Fixtures |
|---|---|---|
| `transcript.py` | URL parsing, cache hit/miss, yt-dlp fallback, TTL expiry | Mocked `youtube-transcript-api` + temp dir |
| `rule_extractor.py` | Stub returns expected `StrategySpec` shape | Plain-text transcript fixtures |
| `codegen.py` | Templates valid AST/Pine, contain `//@version=6`, `validate_pine` catches missing version | Sample `StrategySpec` instances |
| `data.py` | Symbol routing, period clamping, timeframe validation, cost profile lookup | `requests-mock` for HTTP |
| `runner.py` | See §8.2 below | Synthetic 500-bar OHLCV CSV in `tests/fixtures/` |
| `autotune.py` | Grid converges on known optimum; seed gives deterministic results | Synthetic OHLCV |
| `walkforward.py` | Split windows correct + disjoint; overfit detection fires on crafted IS≫OOS strategy | Synthetic OHLCV |
| `storage.py` | Slug collisions, load/save round-trip, `list_runs` ordering | Temp dir |
| `errors.py` additions | All new error types serialize to expected JSON shape | — |

### 8.2 Security tests — `tests/unit/yt_strategy/test_runner_sandbox.py`

Most important test file in the project. The runner exec's LLM-generated code; sandbox leaks would be a backdoor.

**Malicious code MUST be rejected** — parametrized:

```python
MALICIOUS_SAMPLES = [
    ("import os",                                        "SecurityViolation"),
    ("__import__('os')",                                 "SecurityViolation"),
    ("open('/etc/passwd').read()",                       "SecurityViolation"),
    ("eval('1+1')",                                      "SecurityViolation"),
    ("exec('print(1)')",                                 "SecurityViolation"),
    ("import subprocess",                                "SecurityViolation"),
    ("import socket",                                    "SecurityViolation"),
    ("import urllib",                                    "SecurityViolation"),
    ("import requests",                                  "SecurityViolation"),
    ("while True: pass",                                 "Timeout"),
    ("x = [0] * 10**10",                                 "MemoryExceeded"),
    ("globals()['__builtins__']",                        "SecurityViolation"),
    ("getattr(__builtins__, 'eval')",                    "SecurityViolation"),
    ("().__class__.__bases__[0].__subclasses__()",       "SecurityViolation"),
]
```

**Benign code MUST pass** — known-good strategies from `backtesting.py` docs (SmaCross, RsiOscillator, BBands). Proves the sandbox doesn't reject legitimate patterns.

### 8.3 Integration tests — `tests/integration/test_mcp_tools.py`

Real MCP stdio handshake using the pattern already verified in this project (initialize → tools/list → tools/call).

```python
def test_yt_extract_strategy_returns_expected_shape():
    # Stable-id is a pinned YT video with confirmed auto-captions, chosen during
    # implementation and recorded in tests/fixtures/yt_stable_ids.json.
    result = mcp_call("yt_extract_strategy", {"url": STABLE_YT_URL})
    assert "transcript" in result and "python_skeleton" in result and "pine_skeleton" in result

def test_run_strategy_backtest_with_synthetic_strategy():
    result = mcp_call("run_strategy_backtest", {
        "strategy_code": SMA_CROSS_FIXTURE,
        "symbol": "FIXTURE_AAPL", "timeframe": "1d", "period": "2y",
    })
    assert result["out_of_sample"]["sharpe"] == pytest.approx(KNOWN_VALUE, rel=0.01)

def test_auto_tune_converges_on_known_optimum():
    result = mcp_call("auto_tune_strategy", {...})
    assert result["best_params"]["rsi_period"] == 14
```

The integration suite supplies a synthetic OHLCV via a `FIXTURE_*` symbol prefix that `data.py` routes to a local CSV instead of upstream sources, keeping tests hermetic.

### 8.4 Snapshot tests — Pine output

`tests/snapshot/test_pine_codegen.py`: three canonical Python strategy fixtures (SMA cross, RSI mean-reversion, Bollinger breakout). Generated Pine v6 is byte-compared against `tests/fixtures/pine/*.pine`. Refresh via `pytest --snapshot-update` after manual review of TV-verified output.

### 8.5 Explicitly out of scope
- "Does Claude write good strategies." Behavioral property of the LLM.
- YouTube API reliability. Upstream concern; we test graceful failure, not uptime.
- `backtesting.py` correctness. Library responsibility.

### 8.6 CI
Add `.github/workflows/test.yml`: runs `pytest tests/unit tests/integration` on PR + main push (existing workflow only covers Docker publish). Extend `pyproject.toml` `[tool.uv] dev-dependencies` with `pytest-mock`, `requests-mock`, `pytest-timeout`.

### 8.7 Coverage target
~80% line coverage on new `yt_strategy/` modules. 100% on `runner.py` security paths — every malicious sample must hit its specific rejection branch.

---

## 9. New dependencies

To be added to `pyproject.toml` `[project] dependencies`:

| Package | Why |
|---|---|
| `backtesting>=0.3.3` | Backtest engine |
| `youtube-transcript-api>=0.6.2` | Primary transcript fetcher |
| `yt-dlp>=2025.01.01` | Fallback transcript fetcher (also handles age-gated / restricted videos) — date-based versioning; pin to the latest release at implementation time |
| `ta>=0.11.0` | Technical-analysis indicators in user strategy code (lightweight pure-Python; avoids TA-Lib C dep) |
| `scikit-optimize>=0.10.0` | Backend for `auto_tune` Bayesian/skopt mode |
| `Pillow>=10` | Required by `backtesting.plot()` for PNG rendering |

To `[tool.uv] dev-dependencies`:

| Package | Why |
|---|---|
| `pytest-mock>=3.12` | Cleaner mocking |
| `requests-mock>=1.12` | HTTP fixtures |
| `pytest-timeout>=2.3` | Hard timeouts on integration tests |

---

## 10. Configuration / env vars

New env vars (all optional, sensible defaults; documented in `.env.example`):

| Var | Default | Purpose |
|---|---|---|
| `RUNNER_TIMEOUT_S` | `60` | Subprocess wall-clock cap for strategy exec |
| `RUNNER_MEMORY_MB` | `1000` | Subprocess RLIMIT_AS cap |
| `YT_TRANSCRIPT_CACHE_TTL_H` | `24` | Transcript cache lifetime |
| `STRATEGY_STORAGE_DIR` | `~/.tradingview_mcp_data/strategies` | Persisted runs root |
| `BINANCE_API_BASE` | `https://api.binance.com` | Override for testing or geo-blocked regions |

No new secrets required.

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Sandbox escape via novel CPython internals abuse | Defense in depth: AST scan + restricted namespace + subprocess + RLIMIT. Each layer independently sufficient for most paths; combined for layered failure. Security test suite (§8.2) makes regressions visible. |
| YouTube blocks the transcript API or removes auto-captions | `yt-dlp` fallback covers most blocked cases. Future `transcript_override` param for hard fails. |
| LLM generates strategies that look great IS but die OOS | Walk-forward is on by default. `overfit_flag` raised when OOS Sharpe < 50% of IS Sharpe. Report shows both side-by-side — user can't miss it. |
| Auto-tune produces no-trades or pathological optima | `NoTrades` error class; `auto_tune` returns `all_trials` sorted so degenerate optima are visible. |
| Binance API geo-blocks (e.g., US) | `BINANCE_API_BASE` env override. Document `https://data-api.binance.vision` as US-friendly read-only alternative. |
| Pine generated doesn't match Python behavior 1:1 | Pine is best-effort; report explicitly states "Pine is a faithful translation but the Python backtest is the source of truth for metrics." Snapshot tests catch generator regressions, not translation fidelity. |
| Strategy storage grows unbounded | `list_runs` supports pruning; phase-2 ticket to add `purge_runs(older_than)` if it becomes a problem. Out of MVP scope. |

---

## 12. Open questions

None outstanding at design close. Implementation may surface decisions worth a quick check-in (e.g., exact param-grid schema, error JSON key naming) — those go through the implementation plan, not back to design.

---

## 13. Out-of-MVP follow-ups (Phase 1.5 / Phase 2)

- Browser-driven TradingView UI access (Phase 2 — separate spec).
- Standalone Pine generator MCP tool (Phase 3 — separate spec).
- Multi-asset backtests (would require `vectorbt` swap).
- Fundamental / sentiment / on-chain data inputs.
- `transcript_override` param for manual transcript input.
- `purge_runs` storage hygiene tool.
- Monte-Carlo trade-order randomization for metric confidence intervals.
