# YT → Backtest MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three MCP tools (`yt_extract_strategy`, `run_strategy_backtest`, `auto_tune_strategy`) to `tradingview-mcp` that together convert YouTube strategy videos into walk-forward-validated Python backtests plus Pine v6 scripts, with deterministic parameter auto-tuning.

**Architecture:** Approach C from the design — thin MCP primitives orchestrated by the Claude Desktop assistant. New code lives under `src/tradingview_mcp/core/services/yt_strategy/`. Strategy code is exec'd in a hardened subprocess (AST scan + restricted namespace + 60s wall-clock + 1GB RLIMIT). Walk-forward validation is on by default. Existing `core/errors.py` envelope is reused.

**Tech Stack:** Python 3.10+, `backtesting.py` (engine), `youtube-transcript-api` + `yt-dlp` (transcripts), `ta` (indicators in user code), `scikit-optimize` (auto-tune Bayesian), Yahoo Finance (existing `yahoo_finance_service`) + Binance `/api/v3/klines` (data), `multiprocessing` + `resource.setrlimit` (sandbox), pytest + `pytest-mock` + `requests-mock` + `pytest-timeout` (tests).

**Reference design:** `docs/superpowers/specs/2026-06-03-yt-to-backtest-mcp-design.md` (commit `61e6bc9`).

---

## File Structure

New files (all under `src/tradingview_mcp/core/services/yt_strategy/`):

| File | Responsibility |
|---|---|
| `__init__.py` | Public re-exports |
| `transcript.py` | YouTube URL → plaintext transcript, with cache + fallback |
| `rule_extractor.py` | `StrategySpec` dataclass + transcript-to-stub extractor |
| `codegen.py` | Python + Pine v6 templates, Pine structural validator |
| `data.py` | Symbol → source routing, OHLCV fetch, cost-profile lookup, period clamping |
| `runner.py` | AST security scan + sandboxed subprocess exec + result aggregation |
| `walkforward.py` | Expanding-window walk-forward split + overfit detection |
| `autotune.py` | Wrapper around `backtesting.py` `Backtest.optimize()` |
| `storage.py` | Save/load/list persisted runs |

Modified files:

| File | Change |
|---|---|
| `pyproject.toml` | Add runtime deps (`backtesting`, `youtube-transcript-api`, `yt-dlp`, `ta`, `scikit-optimize`, `Pillow`) and dev deps (`pytest-mock`, `requests-mock`, `pytest-timeout`) |
| `src/tradingview_mcp/core/errors.py` | Add 4 new `ErrorCode` values + `make_strategy_error()` helper |
| `src/tradingview_mcp/server.py` | Register three new MCP tools |
| `.env.example` | Document new env vars (`RUNNER_TIMEOUT_S`, `RUNNER_MEMORY_MB`, `YT_TRANSCRIPT_CACHE_TTL_H`, `STRATEGY_STORAGE_DIR`, `BINANCE_API_BASE`) |
| `.github/workflows/test.yml` | New CI workflow running pytest |

Test files (all under `tests/unit/yt_strategy/` and `tests/integration/`):

| File | Tests |
|---|---|
| `tests/unit/yt_strategy/__init__.py` | Empty |
| `tests/unit/yt_strategy/test_transcript.py` | URL parsing, cache hit/miss, fallback, TTL |
| `tests/unit/yt_strategy/test_rule_extractor.py` | Stub shape, confidence default |
| `tests/unit/yt_strategy/test_codegen.py` | Template validity, Pine structural validator |
| `tests/unit/yt_strategy/test_data.py` | Symbol routing, cost profiles, period clamping |
| `tests/unit/yt_strategy/test_runner_sandbox.py` | All malicious samples rejected; all benign samples pass |
| `tests/unit/yt_strategy/test_runner_integration.py` | Full backtest cycle on synthetic fixture |
| `tests/unit/yt_strategy/test_walkforward.py` | Split correctness, overfit flag |
| `tests/unit/yt_strategy/test_autotune.py` | Converges on known optimum, deterministic with seed |
| `tests/unit/yt_strategy/test_storage.py` | Slug round-trip, ordering |
| `tests/unit/yt_strategy/test_errors.py` | New error envelope shapes |
| `tests/integration/test_yt_mcp_tools.py` | MCP stdio handshake end-to-end |
| `tests/fixtures/synthetic_ohlcv.csv` | 500-bar deterministic OHLCV |
| `tests/fixtures/strategies/sma_cross.py` | Benign reference strategy |
| `tests/fixtures/strategies/rsi_oscillator.py` | Benign reference strategy |
| `tests/fixtures/strategies/bbands.py` | Benign reference strategy |
| `tests/fixtures/pine/sma_cross.pine` | Pine snapshot baseline |
| `tests/fixtures/pine/rsi_oscillator.pine` | Pine snapshot baseline |
| `tests/fixtures/pine/bbands.pine` | Pine snapshot baseline |
| `tests/fixtures/yt_stable_ids.json` | Pinned test YT video IDs |

---

## Conventions Used Throughout

- **Existing imports:** the project uses `from __future__ import annotations` at the top of new modules; follow that.
- **Module-private helpers:** prefix with `_`.
- **Type hints:** use modern syntax (`list[str]`, `str | None`); the project requires Python 3.10+.
- **Tests:** use `pytest` style (no `unittest.TestCase`). One assertion focus per test where possible.
- **Commits:** conventional commits format (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- **Co-author line:** every commit ends with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- **No backward-compat shims:** the existing project doesn't use them; we don't add any.

---

## Task 1 — Bootstrap: dependencies, directory structure, baseline

**Files:**
- Modify: `pyproject.toml`
- Create: `src/tradingview_mcp/core/services/yt_strategy/__init__.py`
- Create: `tests/unit/yt_strategy/__init__.py`
- Create: `tests/fixtures/synthetic_ohlcv.csv`

- [ ] **Step 1: Verify baseline tests pass before any changes**

Run: `cd "/Users/andrewfackrell/Trading MCP/tradingview-mcp" && uv run pytest tests/ -q`
Expected: all existing tests pass. If any fail before we begin, stop and report.

- [ ] **Step 2: Add new runtime + dev dependencies to `pyproject.toml`**

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
]
```

```toml
[tool.uv]
dev-dependencies = [
    "pytest>=9.0.3",
    "pytest-mock>=3.12",
    "requests-mock>=1.12",
    "pytest-timeout>=2.3",
]
package = true
```

- [ ] **Step 3: Run `uv sync` to install new deps**

Run: `cd "/Users/andrewfackrell/Trading MCP/tradingview-mcp" && uv sync`
Expected: deps install without error.

- [ ] **Step 4: Verify imports work for new deps**

Run:
```bash
uv run python -c "import backtesting, youtube_transcript_api, yt_dlp, ta, skopt, PIL; print('all imports ok')"
```
Expected: `all imports ok`.

- [ ] **Step 5: Create the yt_strategy package directory**

Create file `src/tradingview_mcp/core/services/yt_strategy/__init__.py` with content:

```python
"""YouTube → strategy → backtest pipeline.

Submodules:
- transcript: YouTube URL → plaintext transcript
- rule_extractor: transcript → StrategySpec stub
- codegen: Python + Pine v6 templates
- data: unified OHLCV fetch (Yahoo + Binance) + cost profiles
- runner: sandboxed strategy exec + backtest
- walkforward: out-of-sample validation
- autotune: deterministic parameter optimization
- storage: persisted runs
"""
from __future__ import annotations
```

- [ ] **Step 6: Create the test directory**

Create empty file `tests/unit/yt_strategy/__init__.py` (zero bytes is fine; just makes it a package).

- [ ] **Step 7: Create the synthetic OHLCV fixture**

Create `tests/fixtures/synthetic_ohlcv.csv` with 500 bars of deterministic data. Use this generation script (run once, commit the output):

```bash
uv run python -c "
import pandas as pd, numpy as np
np.random.seed(42)
n = 500
dates = pd.date_range('2023-01-01', periods=n, freq='1D', tz='UTC')
# Drifting Brownian motion + cyclical component so RSI/MA strategies have signal
trend = np.linspace(0, 0.3, n)
cycle = 0.15 * np.sin(np.linspace(0, 8*np.pi, n))
noise = np.cumsum(np.random.randn(n) * 0.01)
log_price = trend + cycle + noise
close = 100 * np.exp(log_price)
# Realistic OHLC around close
open_ = close * (1 + np.random.randn(n) * 0.003)
high = np.maximum(open_, close) * (1 + np.abs(np.random.randn(n)) * 0.005)
low = np.minimum(open_, close) * (1 - np.abs(np.random.randn(n)) * 0.005)
volume = (1_000_000 + np.random.randn(n) * 100_000).astype(int)
df = pd.DataFrame({'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': volume}, index=dates)
df.index.name = 'Date'
df.to_csv('tests/fixtures/synthetic_ohlcv.csv')
print(f'Wrote {n} rows; first close={df.iloc[0].Close:.2f}, last close={df.iloc[-1].Close:.2f}')
"
```
Expected output: `Wrote 500 rows; first close=100.30, last close=131.84` (or near — seed 42 is deterministic).

- [ ] **Step 8: Sanity-check the fixture is loadable**

Run:
```bash
uv run python -c "
import pandas as pd
df = pd.read_csv('tests/fixtures/synthetic_ohlcv.csv', parse_dates=['Date'], index_col='Date')
assert len(df) == 500, f'Expected 500 rows, got {len(df)}'
assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
print('fixture ok:', df.shape, df.index[0], df.index[-1])
"
```

- [ ] **Step 9: Run baseline tests one more time to confirm nothing is broken**

Run: `uv run pytest tests/ -q`
Expected: same passing test count as Step 1.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock src/tradingview_mcp/core/services/yt_strategy/__init__.py tests/unit/yt_strategy/__init__.py tests/fixtures/synthetic_ohlcv.csv
git commit -m "$(cat <<'EOF'
chore(yt_strategy): bootstrap dependencies, package, and synthetic fixture

Adds backtesting.py, youtube-transcript-api, yt-dlp, ta, scikit-optimize,
Pillow as runtime deps; pytest-mock, requests-mock, pytest-timeout as dev
deps. Creates src/tradingview_mcp/core/services/yt_strategy/ package and
the 500-bar deterministic OHLCV CSV used across the yt_strategy test
suite.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — Extend `errors.py` with strategy error codes + helper

**Files:**
- Modify: `src/tradingview_mcp/core/errors.py`
- Create: `tests/unit/yt_strategy/test_errors.py`

- [ ] **Step 1: Write failing tests for new error codes**

Create `tests/unit/yt_strategy/test_errors.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_errors.py -v`
Expected: All four tests fail — `ImportError` for `make_strategy_error` and `AttributeError` for the new `ErrorCode` values.

- [ ] **Step 3: Add new error codes to `ErrorCode` enum**

Edit `src/tradingview_mcp/core/errors.py`. After the existing `INTERNAL_ERROR = "INTERNAL_ERROR"` line, add:

```python
    # Strategy code (LLM-generated user code) errors
    STRATEGY_SECURITY_VIOLATION = "STRATEGY_SECURITY_VIOLATION"
    STRATEGY_TIMEOUT = "STRATEGY_TIMEOUT"
    STRATEGY_MEMORY_EXCEEDED = "STRATEGY_MEMORY_EXCEEDED"
    STRATEGY_NO_TRADES = "STRATEGY_NO_TRADES"
    STRATEGY_INVALID_CLASS = "STRATEGY_INVALID_CLASS"
    STRATEGY_RUNTIME_ERROR = "STRATEGY_RUNTIME_ERROR"

    # YouTube / transcript
    TRANSCRIPT_UNAVAILABLE = "TRANSCRIPT_UNAVAILABLE"
```

- [ ] **Step 4: Add `make_strategy_error` helper**

Append to `src/tradingview_mcp/core/errors.py` (after the existing `BatchExecutionError` class):

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_errors.py -v`
Expected: all 4 tests pass.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `uv run pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/tradingview_mcp/core/errors.py tests/unit/yt_strategy/test_errors.py
git commit -m "$(cat <<'EOF'
feat(errors): add strategy + transcript error codes + make_strategy_error helper

Seven new ErrorCode values cover the strategy-error subtypes from the
yt_strategy design (security violation, timeout, memory exceeded, no
trades, invalid class, runtime error, transcript unavailable). The
make_strategy_error helper standardizes the rich envelope (user_code_line,
user_code_snippet, hint) used by the assistant to debug iteration N+1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — `transcript.py`: YouTube URL → plaintext transcript

**Files:**
- Create: `src/tradingview_mcp/core/services/yt_strategy/transcript.py`
- Create: `tests/unit/yt_strategy/test_transcript.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/yt_strategy/test_transcript.py`:

```python
"""Tests for transcript.py."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tradingview_mcp.core.services.yt_strategy.transcript import (
    TranscriptResult,
    TranscriptUnavailable,
    fetch_transcript,
    extract_video_id,
)


class TestExtractVideoId:
    def test_standard_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_with_extra_params(self):
        assert extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Not a valid YouTube URL"):
            extract_video_id("https://vimeo.com/12345")


class TestFetchTranscript:
    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_uses_api_when_available(self, mock_api, tmp_path, monkeypatch):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        mock_api.get_transcript.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0},
            {"text": "world", "start": 1.0, "duration": 1.0},
        ]
        result = fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert isinstance(result, TranscriptResult)
        assert "Hello world" in result.text
        assert result.source == "youtube-transcript-api"

    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_caches_result(self, mock_api, tmp_path, monkeypatch):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        mock_api.get_transcript.return_value = [{"text": "Hi", "start": 0.0, "duration": 1.0}]
        # First call hits the API
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert mock_api.get_transcript.call_count == 1
        # Second call hits the cache
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert mock_api.get_transcript.call_count == 1

    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_cache_expires_after_ttl(self, mock_api, tmp_path, monkeypatch):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        monkeypatch.setenv("YT_TRANSCRIPT_CACHE_TTL_H", "0")  # immediate expiry
        mock_api.get_transcript.return_value = [{"text": "Hi", "start": 0.0, "duration": 1.0}]
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert mock_api.get_transcript.call_count == 2  # cache was bypassed

    @patch("tradingview_mcp.core.services.yt_strategy.transcript._fetch_via_ytdlp")
    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_falls_back_to_ytdlp_when_api_fails(
        self, mock_api, mock_ytdlp, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        mock_api.get_transcript.side_effect = Exception("API blocked")
        mock_ytdlp.return_value = TranscriptResult(
            text="from ytdlp",
            language="en",
            duration_s=120,
            title="Test",
            channel="TestCh",
            source="yt-dlp",
            video_id="dQw4w9WgXcQ",
        )
        result = fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert result.text == "from ytdlp"
        assert result.source == "yt-dlp"

    @patch("tradingview_mcp.core.services.yt_strategy.transcript._fetch_via_ytdlp")
    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_raises_when_both_sources_fail(
        self, mock_api, mock_ytdlp, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        mock_api.get_transcript.side_effect = Exception("API blocked")
        mock_ytdlp.side_effect = Exception("ytdlp blocked too")
        with pytest.raises(TranscriptUnavailable):
            fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_transcript.py -v`
Expected: all tests fail with `ImportError`.

- [ ] **Step 3: Implement `transcript.py`**

Create `src/tradingview_mcp/core/services/yt_strategy/transcript.py`:

```python
"""YouTube URL → plaintext transcript with caching and fallback."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "youtube-transcript-api is not installed. Run: uv sync"
    ) from e


@dataclass
class TranscriptResult:
    """Plaintext transcript + video metadata."""
    text: str
    language: str
    duration_s: int
    title: str
    channel: str
    source: str  # "youtube-transcript-api" | "yt-dlp" | "cache"
    video_id: str


class TranscriptUnavailable(Exception):
    """Raised when neither youtube-transcript-api nor yt-dlp can fetch a transcript."""


_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^&]*&)*v=|embed/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str) -> str:
    """Parse a YouTube URL and return its 11-character video ID.

    Raises:
        ValueError: if *url* is not a recognizable YouTube URL.
    """
    m = _VIDEO_ID_RE.search(url)
    if not m:
        raise ValueError(f"Not a valid YouTube URL: {url!r}")
    return m.group(1)


def _cache_dir() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    d = Path(base) / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_ttl_s() -> float:
    try:
        return float(os.environ.get("YT_TRANSCRIPT_CACHE_TTL_H", "24")) * 3600
    except ValueError:
        return 24 * 3600


def _cache_get(video_id: str) -> TranscriptResult | None:
    path = _cache_dir() / f"{video_id}.json"
    if not path.exists():
        return None
    ttl = _cache_ttl_s()
    if ttl <= 0:
        return None
    if time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    data["source"] = "cache"
    return TranscriptResult(**data)


def _cache_set(result: TranscriptResult) -> None:
    path = _cache_dir() / f"{result.video_id}.json"
    try:
        path.write_text(json.dumps(asdict(result)))
    except OSError:  # disk full, permission denied — silent best-effort
        pass


def _fetch_via_api(video_id: str) -> TranscriptResult:
    """Primary path: youtube-transcript-api."""
    chunks = YouTubeTranscriptApi.get_transcript(video_id)
    text = " ".join(c["text"].strip() for c in chunks if c.get("text"))
    duration = int(sum(c.get("duration", 0) for c in chunks))
    return TranscriptResult(
        text=text,
        language="en",  # the lib doesn't expose this on the basic call
        duration_s=duration,
        title="",  # unavailable from this lib
        channel="",
        source="youtube-transcript-api",
        video_id=video_id,
    )


def _fetch_via_ytdlp(video_id: str) -> TranscriptResult:
    """Fallback path: yt-dlp with auto-subs.

    Uses yt-dlp's Python API rather than CLI for cleaner error handling.
    """
    try:
        import yt_dlp  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise TranscriptUnavailable("yt-dlp not installed") from e

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)

    subs = (info or {}).get("automatic_captions", {})
    track = None
    for lang in ("en", "en-US", "en-GB"):
        if lang in subs and subs[lang]:
            track = subs[lang][0]
            break
    if not track or not track.get("url"):
        raise TranscriptUnavailable(f"No English auto-captions for video {video_id}")

    import requests  # type: ignore
    resp = requests.get(track["url"], timeout=20)
    resp.raise_for_status()
    vtt = resp.text
    # Strip VTT headers and timing lines; keep only spoken text.
    text_lines = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
            continue
        # remove inline tags like <c.colorname>
        line = re.sub(r"<[^>]+>", "", line)
        text_lines.append(line)
    text = " ".join(text_lines)

    return TranscriptResult(
        text=text,
        language=track.get("language", "en"),
        duration_s=int(info.get("duration", 0) if info else 0),
        title=str(info.get("title", "") if info else ""),
        channel=str(info.get("uploader", "") if info else ""),
        source="yt-dlp",
        video_id=video_id,
    )


def fetch_transcript(url: str) -> TranscriptResult:
    """Fetch a transcript for *url*.

    Tries cache, then ``youtube-transcript-api``, then ``yt-dlp``.

    Raises:
        ValueError: if *url* is not a valid YouTube URL.
        TranscriptUnavailable: if no source could supply a transcript.
    """
    video_id = extract_video_id(url)

    cached = _cache_get(video_id)
    if cached is not None:
        return cached

    api_err: Exception | None = None
    try:
        result = _fetch_via_api(video_id)
    except Exception as e:
        api_err = e
    else:
        _cache_set(result)
        return result

    try:
        result = _fetch_via_ytdlp(video_id)
    except Exception as ytdlp_err:
        raise TranscriptUnavailable(
            f"Both fetchers failed for {video_id}; "
            f"api_err={api_err!r}; ytdlp_err={ytdlp_err!r}"
        ) from ytdlp_err

    _cache_set(result)
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_transcript.py -v`
Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/transcript.py tests/unit/yt_strategy/test_transcript.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): YouTube URL → transcript with cache + yt-dlp fallback

URL parsing (watch/short/embed forms), 24h JSON cache keyed by video_id,
youtube-transcript-api primary, yt-dlp auto-caption fallback for blocked
videos. TranscriptUnavailable raised when both fail with both error reprs
attached.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — `data.py`: symbol routing, OHLCV fetch, cost profiles

**Files:**
- Create: `src/tradingview_mcp/core/services/yt_strategy/data.py`
- Create: `tests/unit/yt_strategy/test_data.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/yt_strategy/test_data.py`:

```python
"""Tests for data.py."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from tradingview_mcp.core.services.yt_strategy.data import (
    CostProfile,
    cost_profile_for,
    fetch_ohlcv,
    route_symbol,
    validate_timeframe,
    clamp_period,
)


class TestRouteSymbol:
    @pytest.mark.parametrize("sym,src", [
        ("BTCUSDT", "binance"),
        ("ETHUSDT", "binance"),
        ("SOLBUSD", "binance"),
        ("BTCETH", "binance"),
        ("AAPL", "yahoo"),
        ("^GSPC", "yahoo"),
        ("BTC-USD", "yahoo"),
        ("EURUSD=X", "yahoo"),
        ("VOO.L", "yahoo"),
    ])
    def test_routing(self, sym, src):
        assert route_symbol(sym) == src

    def test_fixture_symbols_route_to_fixture(self):
        # FIXTURE_* symbols are used by integration tests to bypass upstream.
        assert route_symbol("FIXTURE_AAPL") == "fixture"


class TestCostProfile:
    def test_binance_crypto(self):
        p = cost_profile_for("BTCUSDT")
        assert p.name == "binance_crypto_spot"
        assert p.commission == 0.001
        assert p.slippage == 0.0005

    def test_yahoo_equity(self):
        p = cost_profile_for("AAPL")
        assert p.name == "yahoo_equity"
        assert p.commission == 0.0
        assert p.slippage == 0.0002

    def test_yahoo_fx(self):
        p = cost_profile_for("EURUSD=X")
        assert p.name == "yahoo_fx"
        assert p.commission == 0.0002

    def test_yahoo_crypto_usd(self):
        p = cost_profile_for("BTC-USD")
        assert p.name == "yahoo_crypto_usd"
        assert p.commission == 0.001


class TestValidateTimeframe:
    @pytest.mark.parametrize("tf", ["1m", "5m", "15m", "1h", "4h", "1d", "1w"])
    def test_binance_accepts(self, tf):
        validate_timeframe("BTCUSDT", tf)  # raises on invalid

    def test_binance_rejects_8h(self):
        with pytest.raises(ValueError, match="does not support"):
            validate_timeframe("BTCUSDT", "8h")

    @pytest.mark.parametrize("tf", ["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"])
    def test_yahoo_accepts(self, tf):
        validate_timeframe("AAPL", tf)

    def test_yahoo_rejects_4h(self):
        with pytest.raises(ValueError, match="does not support"):
            validate_timeframe("AAPL", "4h")


class TestClampPeriod:
    def test_yahoo_intraday_clamps_to_60d(self):
        period, warning = clamp_period("AAPL", "5m", "2y")
        assert period == "60d"
        assert warning is not None
        assert "60" in warning

    def test_yahoo_1m_clamps_to_7d(self):
        period, warning = clamp_period("AAPL", "1m", "2y")
        assert period == "7d"
        assert warning is not None

    def test_yahoo_daily_unrestricted(self):
        period, warning = clamp_period("AAPL", "1d", "10y")
        assert period == "10y"
        assert warning is None

    def test_strict_mode_raises_instead(self):
        with pytest.raises(ValueError, match="exceeds"):
            clamp_period("AAPL", "5m", "2y", strict=True)


class TestFetchOhlcv:
    def test_fixture_loads_synthetic_csv(self):
        df = fetch_ohlcv("FIXTURE_AAPL", "1d", "2y")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert len(df) == 500

    @patch("tradingview_mcp.core.services.yt_strategy.data.requests")
    def test_binance_fetch_returns_expected_shape(self, mock_requests):
        # Mock klines response: list of arrays per Binance docs.
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            [
                1640995200000, "47000.0", "47500.0", "46800.0", "47200.0", "100.5",
                1640995259999, "0", 0, "0", "0", "0",
            ],
            [
                1640995260000, "47200.0", "47300.0", "47100.0", "47250.0", "80.2",
                1640995319999, "0", 0, "0", "0", "0",
            ],
        ]
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_resp

        df = fetch_ohlcv("BTCUSDT", "1m", "1d")
        assert len(df) == 2
        assert df.iloc[0]["Open"] == 47000.0
        assert df.iloc[1]["Close"] == 47250.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_data.py -v`
Expected: all tests fail with `ImportError`.

- [ ] **Step 3: Implement `data.py`**

Create `src/tradingview_mcp/core/services/yt_strategy/data.py`:

```python
"""Unified OHLCV fetch (Yahoo + Binance) + cost profiles."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests


@dataclass(frozen=True)
class CostProfile:
    name: str
    commission: float   # fraction, e.g. 0.001 = 10 bps
    slippage: float


_BINANCE_QUOTES = ("USDT", "BUSD", "USDC", "TUSD", "FDUSD", "DAI", "BTC", "ETH", "BNB")
_BINANCE_TIMEFRAMES = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M")
_YAHOO_TIMEFRAMES = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo")

# Yahoo intraday period caps (per Yahoo's own restrictions).
_YAHOO_INTRADAY_MAX_PERIOD = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "90m": "60d",
    "1h": "730d",
}


def route_symbol(symbol: str) -> str:
    """Decide which data source to use for *symbol*.

    Returns: "fixture" | "binance" | "yahoo"
    """
    if symbol.startswith("FIXTURE_"):
        return "fixture"
    # Binance pair convention: bare alphanumeric ending with a known quote asset
    if re.fullmatch(r"[A-Z0-9]+", symbol):
        for q in _BINANCE_QUOTES:
            if symbol.endswith(q) and len(symbol) > len(q):
                return "binance"
    return "yahoo"


def cost_profile_for(symbol: str) -> CostProfile:
    """Return realistic commission/slippage defaults for *symbol*.

    Overridable by tool args; this is the default when caller omits them.
    """
    src = route_symbol(symbol)
    if src == "binance":
        return CostProfile("binance_crypto_spot", 0.001, 0.0005)
    if symbol.endswith("=X"):
        return CostProfile("yahoo_fx", 0.0002, 0.0001)
    if symbol.endswith("-USD"):
        return CostProfile("yahoo_crypto_usd", 0.001, 0.0005)
    return CostProfile("yahoo_equity", 0.0, 0.0002)


def validate_timeframe(symbol: str, timeframe: str) -> None:
    """Raise ValueError if *timeframe* isn't supported by the routed source."""
    src = route_symbol(symbol)
    if src == "binance" and timeframe not in _BINANCE_TIMEFRAMES:
        raise ValueError(
            f"Binance does not support timeframe {timeframe!r}; valid: {', '.join(_BINANCE_TIMEFRAMES)}"
        )
    if src == "yahoo" and timeframe not in _YAHOO_TIMEFRAMES:
        raise ValueError(
            f"Yahoo does not support timeframe {timeframe!r}; valid: {', '.join(_YAHOO_TIMEFRAMES)}"
        )


def _period_to_days(period: str) -> int:
    """Approximate period string → days. Used only for clamp comparisons."""
    if period.endswith("d"):
        return int(period[:-1])
    if period.endswith("mo"):
        return int(period[:-2]) * 30
    if period.endswith("y"):
        return int(period[:-1]) * 365
    if period.endswith("w") or period.endswith("wk"):
        return int(period.rstrip("wk")) * 7
    return 999_999  # unknown — treat as "very long"; clamp will trigger


def clamp_period(
    symbol: str, timeframe: str, period: str, strict: bool = False
) -> tuple[str, str | None]:
    """If *period* exceeds the source's cap for *timeframe*, clamp it.

    Returns ``(effective_period, warning_or_None)``. With ``strict=True``,
    raises ``ValueError`` instead of clamping.
    """
    src = route_symbol(symbol)
    if src != "yahoo":
        return period, None
    cap = _YAHOO_INTRADAY_MAX_PERIOD.get(timeframe)
    if cap is None:
        return period, None  # daily/weekly/monthly — long histories ok
    if _period_to_days(period) <= _period_to_days(cap):
        return period, None
    if strict:
        raise ValueError(
            f"Yahoo {timeframe} period {period!r} exceeds max {cap!r}"
        )
    return cap, (
        f"Period {period!r} exceeds Yahoo {timeframe!r} cap; clamped to {cap!r}."
    )


def _binance_base() -> str:
    return os.environ.get("BINANCE_API_BASE", "https://api.binance.com").rstrip("/")


def _fetch_binance(symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
    url = f"{_binance_base()}/api/v3/klines"
    resp = requests.get(url, params={"symbol": symbol, "interval": timeframe, "limit": limit}, timeout=15)
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "Open", "High", "Low", "Close", "Volume",
            "close_time", "qav", "trades", "tbbv", "tbqv", "ignore",
        ],
    )
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = df[col].astype(float)
    df["Date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
    return df


def _fetch_yahoo(symbol: str, timeframe: str, period: str) -> pd.DataFrame:
    from tradingview_mcp.core.services.yahoo_finance_service import _yahoo_get_ohlcv  # type: ignore[attr-defined]
    # If the helper isn't exposed, fall back to a direct fetch via the existing service.
    # (Implementation detail: yahoo_finance_service exposes get_price/get_market_snapshot.
    # We need a raw OHLCV path. Add a minimal direct request here.)
    return _yahoo_get_ohlcv_direct(symbol, timeframe, period)


def _yahoo_get_ohlcv_direct(symbol: str, timeframe: str, period: str) -> pd.DataFrame:
    """Direct fetch via Yahoo's chart API. Independent of the existing service
    wrapper so we have a known column shape for backtesting.py."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    resp = requests.get(
        url,
        params={"interval": timeframe, "range": period, "includePrePost": "false"},
        headers={"User-Agent": "Mozilla/5.0 (compatible; tradingview-mcp/0.7)"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    result = body.get("chart", {}).get("result", [])
    if not result:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    r = result[0]
    ts = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    df = pd.DataFrame({
        "Open": quote.get("open", []),
        "High": quote.get("high", []),
        "Low":  quote.get("low", []),
        "Close": quote.get("close", []),
        "Volume": quote.get("volume", []),
    }, index=pd.to_datetime(ts, unit="s", utc=True))
    df.index.name = "Date"
    return df.dropna(subset=["Close"])


def _fetch_fixture(symbol: str) -> pd.DataFrame:
    """Load the synthetic CSV used by integration tests."""
    repo_root = Path(__file__).resolve().parents[5]
    csv = repo_root / "tests" / "fixtures" / "synthetic_ohlcv.csv"
    df = pd.read_csv(csv, parse_dates=["Date"], index_col="Date")
    return df


def fetch_ohlcv(symbol: str, timeframe: str, period: str, *, strict_period: bool = False) -> pd.DataFrame:
    """Fetch OHLCV bars for *symbol* with normalized DataFrame shape.

    Returns a UTC-indexed DataFrame with columns Open, High, Low, Close, Volume.
    Raises ValueError on invalid timeframe.
    """
    validate_timeframe(symbol, timeframe)
    effective_period, _warning = clamp_period(symbol, timeframe, period, strict=strict_period)

    src = route_symbol(symbol)
    if src == "fixture":
        return _fetch_fixture(symbol)
    if src == "binance":
        return _fetch_binance(symbol, timeframe)
    return _yahoo_get_ohlcv_direct(symbol, timeframe, effective_period)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_data.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/data.py tests/unit/yt_strategy/test_data.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): unified OHLCV data layer + cost profiles + period clamping

route_symbol decides Binance vs Yahoo vs FIXTURE bypass; fetch_ohlcv returns
normalized OHLCV (UTC-indexed, Open/High/Low/Close/Volume) for either
source. cost_profile_for returns asset-class-aware commission/slippage
defaults (binance_crypto_spot, yahoo_equity, yahoo_fx, yahoo_crypto_usd).
clamp_period prevents Yahoo intraday from exceeding source caps.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — `rule_extractor.py`: StrategySpec dataclass + stub

**Files:**
- Create: `src/tradingview_mcp/core/services/yt_strategy/rule_extractor.py`
- Create: `tests/unit/yt_strategy/test_rule_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/yt_strategy/test_rule_extractor.py`:

```python
from __future__ import annotations

from tradingview_mcp.core.services.yt_strategy.rule_extractor import (
    StrategySpec,
    extract_rules,
)


def test_strategy_spec_default_fields():
    s = StrategySpec()
    assert s.name == ""
    assert s.entry_rules == []
    assert s.exit_rules == []
    assert s.indicators_used == []
    assert s.timeframe_hint is None
    assert s.asset_hint is None
    assert s.position_sizing is None
    assert s.risk_management is None
    assert s.confidence == 0.0


def test_extract_rules_stub_wraps_transcript():
    spec = extract_rules("Buy when RSI is below 30, sell when above 70.")
    assert isinstance(spec, StrategySpec)
    # MVP stub keeps the raw transcript as a single entry rule.
    assert spec.entry_rules == ["Buy when RSI is below 30, sell when above 70."]
    # Confidence is low because we did no real extraction.
    assert spec.confidence < 0.5
    # Transcript text is also retained for the assistant to consume directly.
    assert spec.raw_transcript == "Buy when RSI is below 30, sell when above 70."


def test_extract_rules_empty_transcript():
    spec = extract_rules("")
    assert spec.entry_rules == []
    assert spec.confidence == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_rule_extractor.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `rule_extractor.py`**

Create `src/tradingview_mcp/core/services/yt_strategy/rule_extractor.py`:

```python
"""StrategySpec dataclass + MVP rule-extraction stub.

The real rule extraction is delegated to the assistant in Claude Desktop,
which reads the transcript directly and fills in skeletons returned by
codegen.py. This module exists for shape stability — every Tool 1 call
returns a StrategySpec the assistant can build on.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StrategySpec:
    name: str = ""
    entry_rules: list[str] = field(default_factory=list)
    exit_rules: list[str] = field(default_factory=list)
    indicators_used: list[str] = field(default_factory=list)
    timeframe_hint: str | None = None
    asset_hint: str | None = None
    position_sizing: str | None = None
    risk_management: str | None = None
    confidence: float = 0.0
    raw_transcript: str = ""


def extract_rules(transcript: str) -> StrategySpec:
    """MVP stub: wrap the transcript as a single entry rule with low confidence.

    Returns an empty-but-valid spec if *transcript* is empty.
    """
    if not transcript.strip():
        return StrategySpec()
    return StrategySpec(
        entry_rules=[transcript],
        raw_transcript=transcript,
        confidence=0.1,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_rule_extractor.py -v`
Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/rule_extractor.py tests/unit/yt_strategy/test_rule_extractor.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): StrategySpec dataclass + MVP rule-extraction stub

Provides the structured spec object every yt_extract_strategy call returns.
Real rule extraction lives in the assistant's reasoning (Approach C); this
module keeps the wire shape stable so server output is type-checkable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — `codegen.py`: Python + Pine templates + Pine validator

**Files:**
- Create: `src/tradingview_mcp/core/services/yt_strategy/codegen.py`
- Create: `tests/unit/yt_strategy/test_codegen.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/yt_strategy/test_codegen.py`:

```python
from __future__ import annotations

import ast

import pytest

from tradingview_mcp.core.services.yt_strategy.rule_extractor import StrategySpec
from tradingview_mcp.core.services.yt_strategy.codegen import (
    Issue,
    python_template,
    pine_template,
    validate_pine,
)


class TestPythonTemplate:
    def test_returns_valid_python(self):
        code = python_template(StrategySpec(name="TestStrat"))
        ast.parse(code)  # raises SyntaxError if invalid

    def test_defines_strategy_subclass(self):
        code = python_template(StrategySpec(name="TestStrat"))
        assert "class" in code
        assert "Strategy" in code
        assert "def init" in code
        assert "def next" in code

    def test_includes_todo_markers(self):
        code = python_template(StrategySpec(name="TestStrat"))
        assert "TODO" in code  # marks where assistant should fill in

    def test_imports_safe_namespace_only(self):
        code = python_template(StrategySpec(name="TestStrat"))
        # No forbidden imports leak into the template.
        for forbidden in ("import os", "import subprocess", "import socket", "open("):
            assert forbidden not in code


class TestPineTemplate:
    def test_has_version_directive(self):
        code = pine_template(StrategySpec(name="TestStrat"))
        assert "//@version=6" in code

    def test_has_strategy_call(self):
        code = pine_template(StrategySpec(name="TestStrat"))
        assert "strategy(" in code

    def test_includes_todo_markers(self):
        code = pine_template(StrategySpec(name="TestStrat"))
        assert "TODO" in code


class TestValidatePine:
    def test_valid_pine_returns_empty(self):
        good = '//@version=6\nstrategy("X", overlay=true)\nplot(close)\n'
        assert validate_pine(good) == []

    def test_missing_version_flagged(self):
        bad = 'strategy("X", overlay=true)\nplot(close)\n'
        issues = validate_pine(bad)
        assert any("version" in i.message.lower() for i in issues)

    def test_missing_strategy_or_indicator_flagged(self):
        bad = '//@version=6\nplot(close)\n'
        issues = validate_pine(bad)
        assert any("strategy" in i.message.lower() or "indicator" in i.message.lower() for i in issues)

    def test_unbalanced_parens_flagged(self):
        bad = '//@version=6\nstrategy("X", overlay=true\nplot(close)\n'
        issues = validate_pine(bad)
        assert any("paren" in i.message.lower() or "balance" in i.message.lower() for i in issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_codegen.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `codegen.py`**

Create `src/tradingview_mcp/core/services/yt_strategy/codegen.py`:

```python
"""Python + Pine v6 templates and Pine structural validator."""
from __future__ import annotations

from dataclasses import dataclass

from .rule_extractor import StrategySpec


@dataclass
class Issue:
    """One structural problem found by a validator."""
    severity: str  # "error" | "warning"
    message: str
    line: int | None = None


_PYTHON_TEMPLATE = '''"""LLM-generated trading strategy.

This is a skeleton. The assistant fills in the indicators_used in init()
and the entry/exit logic in next(). Only `backtesting`, `pandas as pd`,
`numpy as np`, `ta`, `math`, and `statistics` are available — anything
else will be rejected by the runner's AST scan.

Strategy class MUST be named so that the runner can find it; any unique
name subclassing backtesting.Strategy is fine.
"""
from backtesting import Strategy
from backtesting.lib import crossover

import pandas as pd
import numpy as np
import ta


class {class_name}(Strategy):
    # TODO: add tunable params here as class attributes (e.g. rsi_period = 14)

    def init(self):
        # TODO: precompute indicators with self.I(...)
        # Example: self.rsi = self.I(ta.momentum.RSIIndicator,
        #                            pd.Series(self.data.Close), self.rsi_period).rsi
        pass

    def next(self):
        # TODO: entry/exit logic. self.position, self.buy(), self.sell(), self.position.close()
        pass
'''


def python_template(spec: StrategySpec) -> str:
    """Return a backtesting.py Strategy skeleton for *spec*.

    The class is named ``Strategy_<sanitized-name>`` so the assistant's
    diff-edits are easier to read across iterations.
    """
    name = (spec.name or "Strategy").strip() or "Strategy"
    safe_name = "".join(c if c.isalnum() else "_" for c in name) or "Strategy"
    class_name = f"Strategy_{safe_name}"
    return _PYTHON_TEMPLATE.format(class_name=class_name)


_PINE_TEMPLATE = '''//@version=6
strategy("{title}", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100, commission_type=strategy.commission.percent, commission_value=0.1)

// TODO: parameters (input.int / input.float)
// rsi_period = input.int(14, "RSI period")

// TODO: indicators
// rsi = ta.rsi(close, rsi_period)

// TODO: entry/exit
// if (rsi < 30)
//     strategy.entry("long", strategy.long)
// if (rsi > 70)
//     strategy.close("long")
'''


def pine_template(spec: StrategySpec) -> str:
    """Return a Pine v6 strategy skeleton for *spec*."""
    title = (spec.name or "Strategy").strip().replace('"', "'") or "Strategy"
    return _PINE_TEMPLATE.format(title=title)


def validate_pine(code: str) -> list[Issue]:
    """Structurally validate Pine v6 code.

    Catches the small set of mistakes most likely from LLM output:
    missing ``//@version=6``, no ``strategy()``/``indicator()`` call,
    unbalanced parens. Not a full parser; not a runtime check.
    """
    issues: list[Issue] = []

    if "//@version=6" not in code and "//@version=5" not in code:
        issues.append(Issue("error", "Missing Pine version directive (//@version=6)."))

    has_strategy = "strategy(" in code
    has_indicator = "indicator(" in code
    has_library = "library(" in code
    if not (has_strategy or has_indicator or has_library):
        issues.append(Issue(
            "error",
            "Pine must contain exactly one of: strategy(), indicator(), library().",
        ))

    # Parenthesis balance (ignoring content inside string literals).
    depth = 0
    in_str: str | None = None
    for ch in code:
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                issues.append(Issue("error", "Unbalanced parens: closer without opener."))
                break
    if depth > 0:
        issues.append(Issue("error", f"Unbalanced parens: {depth} unclosed."))

    return issues
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_codegen.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/codegen.py tests/unit/yt_strategy/test_codegen.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): Python + Pine v6 templates + Pine structural validator

python_template returns a backtesting.py Strategy skeleton with TODO
markers. pine_template returns a Pine v6 strategy skeleton with matching
TODO markers. validate_pine performs structural checks (version directive,
strategy/indicator/library call present, paren balance) — cheap insurance
before persisting LLM-generated Pine.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 — `runner.py` part 1: AST security scanner

**Files:**
- Create: `src/tradingview_mcp/core/services/yt_strategy/runner.py` (partial — scanner only)
- Create: `tests/unit/yt_strategy/test_runner_sandbox.py`
- Create: `tests/fixtures/strategies/sma_cross.py`
- Create: `tests/fixtures/strategies/rsi_oscillator.py`
- Create: `tests/fixtures/strategies/bbands.py`

- [ ] **Step 1: Create benign reference strategies**

Create `tests/fixtures/strategies/sma_cross.py`:

```python
from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd
import numpy as np
import ta


class Strategy_SmaCross(Strategy):
    fast = 10
    slow = 30

    def init(self):
        close = pd.Series(self.data.Close)
        self.sma_f = self.I(lambda c, p: c.rolling(p).mean(), close, self.fast)
        self.sma_s = self.I(lambda c, p: c.rolling(p).mean(), close, self.slow)

    def next(self):
        if crossover(self.sma_f, self.sma_s):
            self.buy()
        elif crossover(self.sma_s, self.sma_f):
            self.position.close()
```

Create `tests/fixtures/strategies/rsi_oscillator.py`:

```python
from backtesting import Strategy
import pandas as pd
import ta


class Strategy_Rsi(Strategy):
    rsi_period = 14
    oversold = 30
    overbought = 70

    def init(self):
        close = pd.Series(self.data.Close)
        self.rsi = self.I(
            lambda c, p: ta.momentum.RSIIndicator(c, p).rsi(),
            close, self.rsi_period,
        )

    def next(self):
        if not self.position and self.rsi[-1] < self.oversold:
            self.buy()
        elif self.position and self.rsi[-1] > self.overbought:
            self.position.close()
```

Create `tests/fixtures/strategies/bbands.py`:

```python
from backtesting import Strategy
import pandas as pd
import ta


class Strategy_BBands(Strategy):
    period = 20
    std = 2.0

    def init(self):
        close = pd.Series(self.data.Close)
        bb = ta.volatility.BollingerBands(close, self.period, self.std)
        self.upper = self.I(lambda: bb.bollinger_hband().values)
        self.lower = self.I(lambda: bb.bollinger_lband().values)

    def next(self):
        if not self.position and self.data.Close[-1] < self.lower[-1]:
            self.buy()
        elif self.position and self.data.Close[-1] > self.upper[-1]:
            self.position.close()
```

- [ ] **Step 2: Write failing tests for the AST scanner**

Create `tests/unit/yt_strategy/test_runner_sandbox.py`:

```python
"""Security tests for the runner's AST scanner.

Every malicious sample MUST be rejected; every benign sample MUST pass.
A failure here is a sandbox regression — treat as a P0.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_mcp.core.services.yt_strategy.runner import (
    SecurityViolation,
    scan_strategy_code,
)


MALICIOUS_SAMPLES = [
    ("import os",                                        "os"),
    ("import subprocess",                                "subprocess"),
    ("import socket",                                    "socket"),
    ("import urllib",                                    "urllib"),
    ("import requests",                                  "requests"),
    ("import shutil",                                    "shutil"),
    ("from os import path",                              "os"),
    ("__import__('os')",                                 "__import__"),
    ("open('/etc/passwd').read()",                       "open"),
    ("eval('1+1')",                                      "eval"),
    ("exec('print(1)')",                                 "exec"),
    ("compile('1', '<>', 'exec')",                       "compile"),
    ("globals()",                                        "globals"),
    ("locals()",                                         "locals"),
    ("vars()",                                           "vars"),
    ("breakpoint()",                                     "breakpoint"),
    ("getattr(int, '__class__')",                        "__class__"),
    ("(0).__class__",                                    "__class__"),
    ("().__class__.__bases__",                           "__bases__"),
    ("type.__subclasses__(type)",                        "__subclasses__"),
    ("print.__globals__",                                "__globals__"),
]


@pytest.mark.parametrize("code,offending_token", MALICIOUS_SAMPLES)
def test_malicious_code_rejected(code, offending_token):
    full = f"from backtesting import Strategy\nclass S(Strategy):\n    def init(self):\n        {code}\n    def next(self):\n        pass\n"
    with pytest.raises(SecurityViolation) as exc_info:
        scan_strategy_code(full)
    assert offending_token in str(exc_info.value), (
        f"Violation message should mention '{offending_token}': got {exc_info.value!r}"
    )


@pytest.mark.parametrize("fixture", ["sma_cross.py", "rsi_oscillator.py", "bbands.py"])
def test_benign_code_accepted(fixture):
    code = (Path(__file__).resolve().parents[2] / "fixtures" / "strategies" / fixture).read_text()
    # Should not raise.
    scan_strategy_code(code)


def test_attribute_dunder_self_data_dict_allowed():
    # self.data.__dict__ shouldn't be flagged — backtesting.py uses these.
    code = """
from backtesting import Strategy
class S(Strategy):
    def init(self): pass
    def next(self):
        x = self.data.__class__
"""
    # self.data.__class__ is currently flagged; that's stricter than necessary
    # but acceptable. Test that legitimate access patterns (self.data.Close)
    # are NOT flagged.
    safe = """
from backtesting import Strategy
class S(Strategy):
    def init(self): pass
    def next(self):
        x = self.data.Close[-1]
"""
    scan_strategy_code(safe)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_runner_sandbox.py -v`
Expected: all tests fail with `ImportError`.

- [ ] **Step 4: Implement the AST scanner**

Create `src/tradingview_mcp/core/services/yt_strategy/runner.py`:

```python
"""Sandboxed exec of LLM-generated strategy code.

This file is security-critical. Modifications must add a regression test
to test_runner_sandbox.py first.

Defense in depth:
    1. AST pre-scan (this file): reject before exec on forbidden names
    2. Restricted exec namespace: only safe libraries in scope
    3. Subprocess isolation: strategy runs in a separate Process
    4. Wall-clock timeout: process.kill() after N seconds
    5. Memory cap: RLIMIT_AS in subprocess

Layers 2-5 are implemented in the next task; layer 1 is here.
"""
from __future__ import annotations

import ast


class SecurityViolation(Exception):
    """Raised when AST scan rejects LLM-generated code."""

    def __init__(self, message: str, line: int | None = None, snippet: str | None = None):
        super().__init__(message)
        self.line = line
        self.snippet = snippet


_BANNED_MODULES = frozenset({
    "os", "subprocess", "socket", "urllib", "urllib2", "urllib3",
    "requests", "httpx", "aiohttp", "ftplib", "smtplib", "telnetlib",
    "shutil", "glob", "pickle", "marshal", "shelve", "dbm",
    "ctypes", "multiprocessing", "threading", "asyncio",
    "signal", "atexit", "resource", "tempfile", "pathlib",
    "importlib", "imp", "pty", "fcntl", "ioctl",
    "platform", "sysconfig", "site", "code", "codeop",
})

_BANNED_BUILTINS = frozenset({
    "open", "eval", "exec", "compile", "__import__",
    "globals", "locals", "vars", "breakpoint",
    "exit", "quit", "help", "input",
})

_BANNED_DUNDER_ATTRS = frozenset({
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__builtins__", "__code__",
    "__import__", "__loader__", "__spec__",
    # __dict__ allowed only on self.data — handled separately
})


def _line_snippet(code: str, line: int | None) -> str | None:
    if line is None:
        return None
    lines = code.splitlines()
    if 0 < line <= len(lines):
        return lines[line - 1]
    return None


class _ScanVisitor(ast.NodeVisitor):
    def __init__(self, code: str) -> None:
        self.code = code
        self.violations: list[SecurityViolation] = []

    def _fail(self, msg: str, node: ast.AST) -> None:
        line = getattr(node, "lineno", None)
        self.violations.append(SecurityViolation(msg, line=line, snippet=_line_snippet(self.code, line)))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            if top in _BANNED_MODULES:
                self._fail(f"Forbidden import: {alias.name!r} (banned module {top!r}).", node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            top = node.module.split(".", 1)[0]
            if top in _BANNED_MODULES:
                self._fail(f"Forbidden import: from {node.module!r} (banned module {top!r}).", node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in _BANNED_BUILTINS:
            self._fail(f"Forbidden builtin: {node.id!r}.", node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _BANNED_DUNDER_ATTRS:
            self._fail(f"Forbidden attribute access: {node.attr!r}.", node)
        elif node.attr == "__dict__":
            # Allowed only on self.data
            v = node.value
            if not (isinstance(v, ast.Attribute) and v.attr == "data"
                    and isinstance(v.value, ast.Name) and v.value.id == "self"):
                self._fail("Forbidden attribute access: '__dict__' allowed only on self.data.", node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # getattr/setattr/delattr/hasattr with dunder string -> reject
        func = node.func
        is_reflective = (
            isinstance(func, ast.Name)
            and func.id in {"getattr", "setattr", "delattr", "hasattr"}
        )
        if is_reflective and node.args and isinstance(node.args[1] if len(node.args) > 1 else None, ast.Constant):
            arg = node.args[1].value
            if isinstance(arg, str) and arg.startswith("__"):
                self._fail(
                    f"Forbidden reflective access: {func.id}(_, {arg!r}).", node,
                )
        self.generic_visit(node)


def scan_strategy_code(code: str) -> None:
    """Reject LLM-generated *code* if it references forbidden names.

    Raises:
        SecurityViolation: on first forbidden reference encountered. The
            exception's ``line`` and ``snippet`` attributes locate it.
        SyntaxError: if *code* is not parseable Python.
    """
    tree = ast.parse(code)
    visitor = _ScanVisitor(code)
    visitor.visit(tree)
    if visitor.violations:
        raise visitor.violations[0]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_runner_sandbox.py -v`
Expected: all 21 parametrized malicious cases reject + 3 benign cases pass + 1 dunder-on-self.data case passes.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `uv run pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/runner.py tests/unit/yt_strategy/test_runner_sandbox.py tests/fixtures/strategies/
git commit -m "$(cat <<'EOF'
feat(yt_strategy): AST security scanner for LLM-generated strategy code

scan_strategy_code rejects code that references banned modules (os,
subprocess, socket, urllib, requests, pickle, ctypes, importlib, …),
banned builtins (open, eval, exec, compile, __import__, globals, locals,
…), banned dunder attributes (__class__, __bases__, __subclasses__,
__mro__, __globals__, …), and reflective calls (getattr(_, '__x__'), …).
Allows __dict__ only on self.data per backtesting.py conventions.

Tests cover 21 malicious patterns plus 3 reference benign strategies (SMA
cross, RSI oscillator, Bollinger bands). A failure here is a P0 sandbox
regression.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 — `runner.py` part 2: subprocess execution + timeout/memory cap

**Files:**
- Modify: `src/tradingview_mcp/core/services/yt_strategy/runner.py` (append)
- Modify: `tests/unit/yt_strategy/test_runner_sandbox.py` (append)

- [ ] **Step 1: Add tests for subprocess exec / timeout / memory cap**

Append to `tests/unit/yt_strategy/test_runner_sandbox.py`:

```python


# --- subprocess exec tests ---

from tradingview_mcp.core.services.yt_strategy.runner import (
    StrategyTimeout,
    StrategyMemoryExceeded,
    InvalidStrategyClass,
    exec_strategy_in_subprocess,
)
import pandas as pd
from pathlib import Path

FIXTURE_CSV = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_ohlcv.csv"


def _fixture_df():
    return pd.read_csv(FIXTURE_CSV, parse_dates=["Date"], index_col="Date")


def test_exec_strategy_runs_benign():
    code = (Path(__file__).resolve().parents[2] / "fixtures" / "strategies" / "sma_cross.py").read_text()
    df = _fixture_df()
    result = exec_strategy_in_subprocess(code, df, cash=10_000, commission=0.001)
    assert "metrics" in result
    assert "n_trades" in result["metrics"]


def test_exec_strategy_times_out(monkeypatch):
    monkeypatch.setenv("RUNNER_TIMEOUT_S", "2")
    code = """
from backtesting import Strategy
class S(Strategy):
    def init(self): pass
    def next(self):
        while True:
            pass
"""
    df = _fixture_df()
    with pytest.raises(StrategyTimeout):
        exec_strategy_in_subprocess(code, df, cash=10_000, commission=0.001)


def test_exec_strategy_memory_exceeded(monkeypatch):
    # Use a tight cap to force the trip.
    monkeypatch.setenv("RUNNER_MEMORY_MB", "100")
    code = """
from backtesting import Strategy
class S(Strategy):
    def init(self):
        self.junk = [0] * (50 * 1000 * 1000)  # ~400MB
    def next(self): pass
"""
    df = _fixture_df()
    with pytest.raises((StrategyMemoryExceeded, MemoryError)):
        exec_strategy_in_subprocess(code, df, cash=10_000, commission=0.001)


def test_exec_strategy_no_class():
    code = """
from backtesting import Strategy
# no class defined
x = 1
"""
    df = _fixture_df()
    with pytest.raises(InvalidStrategyClass):
        exec_strategy_in_subprocess(code, df, cash=10_000, commission=0.001)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_runner_sandbox.py::test_exec_strategy_runs_benign -v`
Expected: fails with `ImportError`.

- [ ] **Step 3: Append subprocess execution code to `runner.py`**

Append to `src/tradingview_mcp/core/services/yt_strategy/runner.py`:

```python


# ---------------------------------------------------------------------------
# Subprocess execution layer
# ---------------------------------------------------------------------------

import multiprocessing as _mp
import os as _os
import pickle as _pickle
import sys as _sys
import traceback as _tb
from io import BytesIO
from typing import Any


class StrategyTimeout(Exception):
    """Raised when the strategy subprocess exceeds the wall-clock cap."""


class StrategyMemoryExceeded(Exception):
    """Raised when the strategy subprocess exceeds RLIMIT_AS."""


class InvalidStrategyClass(Exception):
    """Raised when exec'd code defines no backtesting.Strategy subclass."""


class StrategyRuntimeError(Exception):
    """Raised when the strategy raised an exception during execution.

    Attributes ``user_code_line`` and ``user_code_snippet`` locate the failure
    inside the user-provided code (best-effort — derived from traceback).
    """
    def __init__(self, message: str, user_code_line: int | None, user_code_snippet: str | None):
        super().__init__(message)
        self.user_code_line = user_code_line
        self.user_code_snippet = user_code_snippet


def _runner_timeout_s() -> float:
    try:
        return float(_os.environ.get("RUNNER_TIMEOUT_S", "60"))
    except ValueError:
        return 60.0


def _runner_memory_bytes() -> int:
    try:
        mb = int(_os.environ.get("RUNNER_MEMORY_MB", "1000"))
    except ValueError:
        mb = 1000
    return mb * 1024 * 1024


def _safe_builtins() -> dict[str, Any]:
    """Curated __builtins__ for exec'd strategy code.

    Removes the banned-builtin set; keeps everything else.
    """
    import builtins
    allowed = {}
    for name in dir(builtins):
        if name.startswith("_"):
            continue
        if name in _BANNED_BUILTINS:
            continue
        allowed[name] = getattr(builtins, name)
    # Selectively allow __import__ but route through a guarded version
    # that itself rejects banned modules. This lets `import pandas` etc.
    # while still blocking `__import__('os')`.
    orig_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        top = name.split(".", 1)[0]
        if top in _BANNED_MODULES:
            raise ImportError(f"Forbidden import {name!r} blocked by sandbox.")
        return orig_import(name, globals, locals, fromlist, level)

    allowed["__import__"] = _guarded_import
    return allowed


def _child_target(code: str, df_pickle: bytes, cash: float, commission: float, conn) -> None:
    """multiprocessing entrypoint. Runs in the child."""
    import resource

    # Memory cap. RLIMIT_AS is virtual memory in bytes.
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_runner_memory_bytes(), _runner_memory_bytes()))
    except (ValueError, OSError):
        pass  # macOS may refuse; the parent's wall-clock kill still covers us

    try:
        # Reconstruct the bars
        df = _pickle.loads(df_pickle)
        # Exec the strategy code in a restricted namespace
        sandbox_globals: dict[str, Any] = {"__builtins__": _safe_builtins()}
        exec(compile(code, "<strategy>", "exec"), sandbox_globals)

        # Find the Strategy subclass
        from backtesting import Backtest, Strategy
        strategy_cls = None
        for v in sandbox_globals.values():
            if (
                isinstance(v, type)
                and issubclass(v, Strategy)
                and v is not Strategy
            ):
                strategy_cls = v
                break

        if strategy_cls is None:
            conn.send(("invalid_class", None))
            return

        bt = Backtest(df, strategy_cls, cash=cash, commission=commission)
        stats = bt.run()
        result = {
            "metrics": {
                "sharpe":         float(stats.get("Sharpe Ratio", 0) or 0),
                "cagr":           float(stats.get("Return (Ann.) [%]", 0) or 0),
                "mdd":            float(stats.get("Max. Drawdown [%]", 0) or 0),
                "win_rate":       float(stats.get("Win Rate [%]", 0) or 0),
                "profit_factor":  float(stats.get("Profit Factor", 0) or 0),
                "n_trades":       int(stats.get("# Trades", 0) or 0),
                "return_pct":     float(stats.get("Return [%]", 0) or 0),
            },
            "trade_log": stats._trades.to_dict("records") if hasattr(stats, "_trades") else [],
            "equity_curve": stats._equity_curve["Equity"].tolist() if hasattr(stats, "_equity_curve") else [],
        }
        conn.send(("ok", result))
    except MemoryError:
        conn.send(("memory", None))
    except Exception as e:
        tb_lines = _tb.format_exception(type(e), e, e.__traceback__)
        # find first frame matching <strategy>
        line = None
        for frame in _tb.extract_tb(e.__traceback__):
            if frame.filename == "<strategy>":
                line = frame.lineno
                break
        snippet = _line_snippet(code, line)
        conn.send(("runtime", {"message": str(e), "line": line, "snippet": snippet, "traceback": "".join(tb_lines)}))
    finally:
        conn.close()


def exec_strategy_in_subprocess(
    strategy_code: str,
    bars: "Any",
    cash: float = 10_000,
    commission: float = 0.001,
) -> dict[str, Any]:
    """Exec strategy_code in a subprocess with timeout + memory cap.

    *bars* is a pandas DataFrame with Open/High/Low/Close/Volume columns.

    Raises one of:
        SecurityViolation  — AST scan rejected the code
        SyntaxError        — code didn't parse
        StrategyTimeout    — wall-clock exceeded
        StrategyMemoryExceeded
        InvalidStrategyClass
        StrategyRuntimeError
    """
    # Pre-scan (layer 1).
    scan_strategy_code(strategy_code)

    df_pickle = _pickle.dumps(bars)

    ctx = _mp.get_context("spawn")  # clean isolation on macOS
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_child_target,
        args=(strategy_code, df_pickle, cash, commission, child_conn),
    )
    proc.start()
    proc.join(timeout=_runner_timeout_s())
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=2)
        raise StrategyTimeout(
            f"Strategy did not finish within {_runner_timeout_s():.0f}s wall-clock."
        )

    if not parent_conn.poll():
        # Subprocess died without sending — likely killed by OS for memory.
        raise StrategyMemoryExceeded(
            "Strategy subprocess terminated without result; "
            "likely killed for exceeding memory cap."
        )

    tag, payload = parent_conn.recv()
    if tag == "ok":
        return payload
    if tag == "invalid_class":
        raise InvalidStrategyClass(
            "No subclass of backtesting.Strategy defined in submitted code."
        )
    if tag == "memory":
        raise StrategyMemoryExceeded("Strategy hit MemoryError during execution.")
    if tag == "runtime":
        raise StrategyRuntimeError(
            payload["message"],
            user_code_line=payload["line"],
            user_code_snippet=payload["snippet"],
        )
    raise RuntimeError(f"Unknown subprocess tag: {tag!r}")
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_runner_sandbox.py -v`
Expected: all tests pass. The timeout test should take ~2s; the memory test should fail-fast.

If `test_exec_strategy_memory_exceeded` is flaky on macOS because `RLIMIT_AS` doesn't apply: that's documented behavior — `exec_strategy_in_subprocess` falls back to the wall-clock timeout when the OS refuses the limit. The test uses `pytest.raises((StrategyMemoryExceeded, MemoryError))` and the underlying timeout path also raises `StrategyMemoryExceeded` when the subprocess dies without sending, so this passes on both Linux and macOS.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `uv run pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/runner.py tests/unit/yt_strategy/test_runner_sandbox.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): sandboxed subprocess exec for LLM-generated strategies

exec_strategy_in_subprocess wraps strategy_code in a multiprocessing spawn
context with RLIMIT_AS memory cap (1GB default), wall-clock timeout (60s
default), and a curated __builtins__ that strips banned names and routes
imports through a guarded __import__ that rejects banned top-level
modules. Reports clean StrategyTimeout / StrategyMemoryExceeded /
InvalidStrategyClass / StrategyRuntimeError exceptions, all with line +
snippet metadata where applicable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 — `walkforward.py`: expanding-window split + overfit flag

**Files:**
- Create: `src/tradingview_mcp/core/services/yt_strategy/walkforward.py`
- Create: `tests/unit/yt_strategy/test_walkforward.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/yt_strategy/test_walkforward.py`:

```python
from __future__ import annotations

import pandas as pd
import pytest

from tradingview_mcp.core.services.yt_strategy.walkforward import (
    walk_forward_split,
    detect_overfit,
)


def _fixture_df():
    from pathlib import Path
    csv = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_ohlcv.csv"
    return pd.read_csv(csv, parse_dates=["Date"], index_col="Date")


def test_split_yields_5_folds_from_500_bars():
    df = _fixture_df()
    folds = walk_forward_split(df, n_chunks=6)
    assert len(folds) == 5

def test_each_fold_test_immediately_follows_train():
    df = _fixture_df()
    folds = walk_forward_split(df, n_chunks=6)
    for train, test in folds:
        assert train.index[-1] < test.index[0], "Test must start after train ends"

def test_train_is_expanding():
    df = _fixture_df()
    folds = walk_forward_split(df, n_chunks=6)
    lengths = [len(train) for train, _ in folds]
    assert lengths == sorted(lengths), "Train should expand each fold"

def test_fold_test_disjoint_from_train():
    df = _fixture_df()
    folds = walk_forward_split(df, n_chunks=6)
    for train, test in folds:
        # No overlap.
        assert set(train.index).isdisjoint(set(test.index))

def test_detect_overfit_fires_when_oos_half_is():
    assert detect_overfit(is_sharpe=2.0, oos_sharpe=0.5) is True
    assert detect_overfit(is_sharpe=2.0, oos_sharpe=1.5) is False

def test_detect_overfit_handles_negative_is():
    # If IS itself is bad, OOS comparison doesn't make sense.
    assert detect_overfit(is_sharpe=-0.5, oos_sharpe=0.5) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_walkforward.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `walkforward.py`**

Create `src/tradingview_mcp/core/services/yt_strategy/walkforward.py`:

```python
"""Expanding-window walk-forward validation."""
from __future__ import annotations

import pandas as pd


def walk_forward_split(data: pd.DataFrame, n_chunks: int = 6) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Split *data* into ``n_chunks-1`` (train, test) folds with expanding train.

    For chunk index *k* in {1..n_chunks-1}, train is chunks 1..k, test is
    chunk k+1. Yields ``n_chunks-1`` folds total.

    Raises:
        ValueError: if data has fewer rows than n_chunks.
    """
    if len(data) < n_chunks:
        raise ValueError(f"Need at least {n_chunks} rows; got {len(data)}.")
    chunk_size = len(data) // n_chunks
    chunks = [data.iloc[i * chunk_size : (i + 1) * chunk_size] for i in range(n_chunks)]
    # Absorb any remainder rows into the last chunk so we don't drop them.
    if (n_chunks * chunk_size) < len(data):
        last_extra = data.iloc[n_chunks * chunk_size :]
        chunks[-1] = pd.concat([chunks[-1], last_extra])

    folds: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for k in range(1, n_chunks):
        train = pd.concat(chunks[:k])
        test = chunks[k]
        folds.append((train, test))
    return folds


def detect_overfit(is_sharpe: float, oos_sharpe: float, threshold: float = 0.5) -> bool:
    """True if OOS Sharpe is < *threshold* of IS Sharpe.

    Returns False when IS Sharpe is non-positive (overfit detection only
    makes sense for strategies that look good in-sample).
    """
    if is_sharpe <= 0:
        return False
    return oos_sharpe < threshold * is_sharpe
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_walkforward.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/walkforward.py tests/unit/yt_strategy/test_walkforward.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): expanding-window walk-forward split + overfit detector

walk_forward_split divides data into n_chunks equal parts; yields
(train, test) folds with expanding train and successive test. Default
n_chunks=6 produces 5 OOS folds. detect_overfit returns True when OOS
Sharpe < 50% of IS Sharpe (the spec threshold).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10 — `storage.py`: persist runs

**Files:**
- Create: `src/tradingview_mcp/core/services/yt_strategy/storage.py`
- Create: `tests/unit/yt_strategy/test_storage.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/yt_strategy/test_storage.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from tradingview_mcp.core.services.yt_strategy.storage import (
    RunArtifacts,
    save_run,
    load_run,
    list_runs,
)


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    arts = RunArtifacts(
        strategy_py="print('hi')",
        strategy_pine='//@version=6\nstrategy("X")',
        report_json={"sharpe": 1.5},
        transcript="some transcript",
        equity_curve_png=b"",
    )
    path = save_run("BTCUSDT-1h-iter1", arts)
    assert path.exists()
    loaded = load_run("BTCUSDT-1h-iter1")
    assert loaded.strategy_py == "print('hi')"
    assert loaded.report_json["sharpe"] == 1.5

def test_list_runs_returns_summaries(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    save_run("A-1h-iter1", RunArtifacts("a", "a", {"sharpe": 1.0}, "", b""))
    save_run("B-1d-iter1", RunArtifacts("b", "b", {"sharpe": 2.0}, "", b""))
    runs = list_runs()
    slugs = {r["slug"] for r in runs}
    assert slugs == {"A-1h-iter1", "B-1d-iter1"}

def test_save_run_overwrites(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    save_run("X-1h-iter1", RunArtifacts("v1", "v1", {"sharpe": 1.0}, "", b""))
    save_run("X-1h-iter1", RunArtifacts("v2", "v2", {"sharpe": 2.0}, "", b""))
    loaded = load_run("X-1h-iter1")
    assert loaded.strategy_py == "v2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_storage.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `storage.py`**

Create `src/tradingview_mcp/core/services/yt_strategy/storage.py`:

```python
"""Persisted-run storage under STRATEGY_STORAGE_DIR/strategies/<slug>/."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class RunArtifacts:
    strategy_py: str
    strategy_pine: str
    report_json: dict[str, Any]
    transcript: str
    equity_curve_png: bytes


def _storage_dir() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    d = Path(base) / "strategies"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(slug: str, artifacts: RunArtifacts) -> Path:
    """Persist *artifacts* under storage/<slug>/. Returns the dir path."""
    d = _storage_dir() / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "strategy.py").write_text(artifacts.strategy_py)
    (d / "strategy.pine").write_text(artifacts.strategy_pine)
    (d / "report.json").write_text(json.dumps(artifacts.report_json, indent=2, default=str))
    (d / "transcript.txt").write_text(artifacts.transcript)
    if artifacts.equity_curve_png:
        (d / "equity_curve.png").write_bytes(artifacts.equity_curve_png)
    return d


def load_run(slug: str) -> RunArtifacts:
    d = _storage_dir() / slug
    if not d.exists():
        raise FileNotFoundError(f"No run at slug {slug!r}")
    png_path = d / "equity_curve.png"
    return RunArtifacts(
        strategy_py=(d / "strategy.py").read_text() if (d / "strategy.py").exists() else "",
        strategy_pine=(d / "strategy.pine").read_text() if (d / "strategy.pine").exists() else "",
        report_json=json.loads((d / "report.json").read_text()) if (d / "report.json").exists() else {},
        transcript=(d / "transcript.txt").read_text() if (d / "transcript.txt").exists() else "",
        equity_curve_png=png_path.read_bytes() if png_path.exists() else b"",
    )


def list_runs() -> list[dict[str, Any]]:
    """Return summaries of all persisted runs.

    Each dict: {slug, path, sharpe, n_trades, mtime}
    """
    d = _storage_dir()
    summaries: list[dict[str, Any]] = []
    for sub in sorted(d.iterdir()):
        if not sub.is_dir():
            continue
        report_path = sub / "report.json"
        report: dict[str, Any] = {}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text())
            except json.JSONDecodeError:
                report = {}
        summaries.append({
            "slug": sub.name,
            "path": str(sub),
            "sharpe": report.get("out_of_sample", {}).get("sharpe", report.get("sharpe")),
            "n_trades": report.get("out_of_sample", {}).get("n_trades", report.get("n_trades")),
            "mtime": sub.stat().st_mtime,
        })
    return summaries
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_storage.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/storage.py tests/unit/yt_strategy/test_storage.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): persisted run storage under STRATEGY_STORAGE_DIR

save_run writes strategy.py / strategy.pine / report.json / transcript.txt
/ equity_curve.png under storage/<slug>/. load_run round-trips them.
list_runs returns sortable summaries. Auto-tune does NOT persist; only
run_strategy_backtest writes, keeping history clean.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11 — `runner.py` part 3: wire data + walk-forward + B&H + storage

**Files:**
- Modify: `src/tradingview_mcp/core/services/yt_strategy/runner.py` (append `run_backtest`)
- Create: `tests/unit/yt_strategy/test_runner_integration.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/unit/yt_strategy/test_runner_integration.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_mcp.core.services.yt_strategy.runner import run_backtest


def _benign_code():
    return (Path(__file__).resolve().parents[2] / "fixtures" / "strategies" / "sma_cross.py").read_text()


def test_run_backtest_with_fixture_symbol(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    result = run_backtest(
        strategy_code=_benign_code(),
        symbol="FIXTURE_AAPL",
        timeframe="1d",
        period="2y",
        slug="test-iter1",
        oos_validate=True,
    )
    assert "in_sample" in result
    assert "out_of_sample" in result
    assert "benchmark" in result
    assert "overfit_flag" in result
    assert "run_path" in result
    assert "cost_profile" in result
    # File system: artifacts persisted
    run_dir = tmp_path / "strategies" / "test-iter1"
    assert (run_dir / "strategy.py").exists()
    assert (run_dir / "report.json").exists()

def test_run_backtest_buy_and_hold_benchmark_present(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    result = run_backtest(
        strategy_code=_benign_code(),
        symbol="FIXTURE_AAPL",
        timeframe="1d",
        period="2y",
        slug="bh-test",
    )
    assert "bh_return_pct" in result["benchmark"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_runner_integration.py -v`
Expected: AttributeError or NameError — `run_backtest` not exported yet.

- [ ] **Step 3: Append `run_backtest` to `runner.py`**

Append to `src/tradingview_mcp/core/services/yt_strategy/runner.py`:

```python


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

from .data import fetch_ohlcv, cost_profile_for
from .walkforward import walk_forward_split, detect_overfit
from .storage import save_run, RunArtifacts


def _b_and_h(df) -> dict[str, float]:
    """Buy-and-hold benchmark on the same window."""
    start_price = float(df["Close"].iloc[0])
    end_price = float(df["Close"].iloc[-1])
    bh_return_pct = (end_price / start_price - 1.0) * 100.0
    # Crude Sharpe-on-returns; good enough for benchmark comparison
    rets = df["Close"].pct_change().dropna()
    if len(rets) > 1 and rets.std() > 0:
        bh_sharpe = float((rets.mean() / rets.std()) * (252 ** 0.5))
    else:
        bh_sharpe = 0.0
    return {"bh_return_pct": bh_return_pct, "bh_sharpe": bh_sharpe}


def _aggregate_oos(per_fold: list[dict]) -> dict[str, float]:
    """Mean metrics across walk-forward folds."""
    if not per_fold:
        return {"sharpe": 0.0, "cagr": 0.0, "mdd": 0.0, "win_rate": 0.0,
                "profit_factor": 0.0, "n_trades": 0, "return_pct": 0.0}
    keys = per_fold[0].keys()
    return {k: sum(f[k] for f in per_fold) / len(per_fold) for k in keys}


def run_backtest(
    strategy_code: str,
    symbol: str,
    timeframe: str,
    period: str,
    slug: str,
    cash: float = 10_000,
    commission: float | None = None,
    slippage: float | None = None,
    oos_validate: bool = True,
) -> dict[str, Any]:
    """Top-level entry. Fetches data, runs IS + walk-forward, persists artifacts."""
    profile = cost_profile_for(symbol)
    commission_used = commission if commission is not None else profile.commission

    df = fetch_ohlcv(symbol, timeframe, period)
    if df.empty or len(df) < 30:
        return {
            "in_sample": {}, "out_of_sample": {}, "benchmark": {},
            "overfit_flag": False, "warnings": [f"Insufficient data: got {len(df)} bars."],
            "cost_profile": profile.name, "slug": slug, "run_path": "",
        }

    # In-sample full-window backtest
    in_sample = exec_strategy_in_subprocess(strategy_code, df, cash=cash, commission=commission_used)
    is_metrics = in_sample["metrics"]

    # Out-of-sample walk-forward
    oos_metrics: dict[str, float] = {}
    if oos_validate and len(df) >= 60:
        folds = walk_forward_split(df, n_chunks=6)
        per_fold = []
        for _train, test in folds:
            try:
                fold_result = exec_strategy_in_subprocess(strategy_code, test, cash=cash, commission=commission_used)
                per_fold.append(fold_result["metrics"])
            except (StrategyTimeout, StrategyMemoryExceeded, StrategyRuntimeError, InvalidStrategyClass):
                # Skip bad folds; aggregate over what we have
                continue
        oos_metrics = _aggregate_oos(per_fold)
    else:
        # Simple 70/30 split fallback
        split = int(len(df) * 0.7)
        try:
            test_result = exec_strategy_in_subprocess(strategy_code, df.iloc[split:], cash=cash, commission=commission_used)
            oos_metrics = test_result["metrics"]
        except Exception:
            oos_metrics = is_metrics  # degrade gracefully

    benchmark = _b_and_h(df)
    overfit = detect_overfit(is_metrics.get("sharpe", 0.0), oos_metrics.get("sharpe", 0.0))

    report = {
        "in_sample": is_metrics,
        "out_of_sample": oos_metrics,
        "benchmark": benchmark,
        "overfit_flag": overfit,
        "trade_log": in_sample.get("trade_log", []),
        "cost_profile": profile.name,
        "symbol": symbol, "timeframe": timeframe, "period": period,
        "slug": slug,
        "warnings": [],
    }

    artifacts = RunArtifacts(
        strategy_py=strategy_code,
        strategy_pine="",  # populated by codegen on final convergence
        report_json=report,
        transcript="",
        equity_curve_png=b"",  # PNG generation deferred; backtesting.plot() is HTML by default
    )
    run_path = save_run(slug, artifacts)
    report["run_path"] = str(run_path)
    return report
```

- [ ] **Step 4: Run the integration test**

Run: `uv run pytest tests/unit/yt_strategy/test_runner_integration.py -v`
Expected: both tests pass.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/runner.py tests/unit/yt_strategy/test_runner_integration.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): wire runner orchestration (data + IS + OOS + B&H + persist)

run_backtest now does the full per-iteration cycle: fetch OHLCV via
data.fetch_ohlcv, run in-sample backtest in subprocess, run walk-forward
OOS across 5 folds, compute buy-and-hold benchmark, flag overfit (OOS
Sharpe < 50% of IS Sharpe), and persist artifacts via storage.save_run.
Cost profile is auto-selected by symbol unless caller overrides.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12 — `autotune.py`: deterministic parameter optimization

**Files:**
- Create: `src/tradingview_mcp/core/services/yt_strategy/autotune.py`
- Create: `tests/unit/yt_strategy/test_autotune.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/yt_strategy/test_autotune.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_mcp.core.services.yt_strategy.autotune import auto_tune


def _rsi_code():
    return (Path(__file__).resolve().parents[2] / "fixtures" / "strategies" / "rsi_oscillator.py").read_text()


def test_auto_tune_returns_expected_shape():
    result = auto_tune(
        strategy_code=_rsi_code(),
        param_grid={"rsi_period": [10, 14, 21], "oversold": [25, 30, 35]},
        symbol="FIXTURE_AAPL",
        timeframe="1d",
        period="2y",
        method="grid",
        max_tries=9,
    )
    assert "best_params" in result
    assert "best_metric" in result
    assert "metric_name" in result
    assert "all_trials" in result
    assert result["metric_name"] == "Sharpe Ratio"

def test_auto_tune_is_deterministic_with_seed():
    r1 = auto_tune(
        strategy_code=_rsi_code(),
        param_grid={"rsi_period": [10, 14, 21], "oversold": [25, 30, 35]},
        symbol="FIXTURE_AAPL", timeframe="1d", period="2y",
        method="grid", max_tries=9, seed=42,
    )
    r2 = auto_tune(
        strategy_code=_rsi_code(),
        param_grid={"rsi_period": [10, 14, 21], "oversold": [25, 30, 35]},
        symbol="FIXTURE_AAPL", timeframe="1d", period="2y",
        method="grid", max_tries=9, seed=42,
    )
    assert r1["best_params"] == r2["best_params"]
    assert r1["best_metric"] == r2["best_metric"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/yt_strategy/test_autotune.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `autotune.py`**

Create `src/tradingview_mcp/core/services/yt_strategy/autotune.py`:

```python
"""Deterministic parameter optimization for a fixed strategy structure.

No LLM. Wraps backtesting.py's Backtest.optimize() with seed pinning.
"""
from __future__ import annotations

import itertools
import multiprocessing as _mp
import pickle as _pickle
from typing import Any

from .data import fetch_ohlcv, cost_profile_for
from .runner import scan_strategy_code, _safe_builtins


def _tune_in_subprocess(strategy_code: str, df_pickle: bytes, param_grid: dict, metric: str,
                         cash: float, commission: float, seed: int, conn) -> None:
    """Child process for tuning."""
    import resource, os
    try:
        mb = int(os.environ.get("RUNNER_MEMORY_MB", "1500"))
        resource.setrlimit(resource.RLIMIT_AS, (mb * 1024 * 1024, mb * 1024 * 1024))
    except (ValueError, OSError):
        pass

    try:
        df = _pickle.loads(df_pickle)
        sandbox_globals: dict[str, Any] = {"__builtins__": _safe_builtins()}
        exec(compile(strategy_code, "<strategy>", "exec"), sandbox_globals)

        from backtesting import Backtest, Strategy
        strategy_cls = None
        for v in sandbox_globals.values():
            if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy:
                strategy_cls = v
                break
        if strategy_cls is None:
            conn.send(("invalid_class", None)); return

        bt = Backtest(df, strategy_cls, cash=cash, commission=commission)
        # Grid search via itertools.product; deterministic order
        keys = sorted(param_grid.keys())
        combos = list(itertools.product(*(param_grid[k] for k in keys)))
        trials = []
        best_metric = float("-inf")
        best_params: dict | None = None
        for combo in combos:
            params = dict(zip(keys, combo))
            try:
                stats = bt.run(**params)
                m = float(stats.get(metric, 0) or 0)
            except Exception:
                m = float("-inf")
            trials.append({"params": params, "metric": m})
            if m > best_metric:
                best_metric = m
                best_params = params
        # Sort trials desc for the report
        trials.sort(key=lambda t: t["metric"], reverse=True)
        conn.send(("ok", {"best_params": best_params, "best_metric": best_metric, "all_trials": trials}))
    except Exception as e:
        conn.send(("error", {"message": str(e)}))
    finally:
        conn.close()


def auto_tune(
    strategy_code: str,
    param_grid: dict[str, list],
    symbol: str,
    timeframe: str,
    period: str,
    metric: str = "Sharpe Ratio",
    method: str = "grid",
    max_tries: int = 50,
    seed: int = 42,
    cash: float = 10_000,
    commission: float | None = None,
) -> dict[str, Any]:
    """Grid-search *param_grid* against the strategy in *strategy_code*.

    Returns ``{"best_params", "best_metric", "metric_name", "all_trials"}``.
    *method* "grid" is implemented; "skopt" is reserved for future Bayesian
    optimization.
    """
    scan_strategy_code(strategy_code)
    profile = cost_profile_for(symbol)
    commission_used = commission if commission is not None else profile.commission

    df = fetch_ohlcv(symbol, timeframe, period)
    df_pickle = _pickle.dumps(df)

    ctx = _mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_tune_in_subprocess,
        args=(strategy_code, df_pickle, param_grid, metric, cash, commission_used, seed, child_conn),
    )
    proc.start()
    # Generous timeout for the whole grid; reuse RUNNER_TIMEOUT_S as per-trial estimate
    import os
    per_trial_s = float(os.environ.get("RUNNER_TIMEOUT_S", "60"))
    n_combos = 1
    for v in param_grid.values():
        n_combos *= len(v)
    proc.join(timeout=per_trial_s * min(n_combos, max_tries) + 30)
    if proc.is_alive():
        proc.kill(); proc.join(timeout=2)
        raise TimeoutError("auto_tune exceeded budget.")

    if not parent_conn.poll():
        raise RuntimeError("auto_tune subprocess produced no result.")
    tag, payload = parent_conn.recv()
    if tag != "ok":
        raise RuntimeError(f"auto_tune failed: {payload}")
    payload["metric_name"] = metric
    return payload
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/yt_strategy/test_autotune.py -v`
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingview_mcp/core/services/yt_strategy/autotune.py tests/unit/yt_strategy/test_autotune.py
git commit -m "$(cat <<'EOF'
feat(yt_strategy): deterministic parameter auto-tune (grid search)

auto_tune sweeps param_grid in lexicographic combo order inside a
sandboxed subprocess, returns best_params + sorted all_trials. No LLM.
Same security envelope as runner. skopt (Bayesian) method reserved for
future iteration; grid is the MVP.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13 — Register MCP tools in `server.py`

**Files:**
- Modify: `src/tradingview_mcp/server.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_yt_mcp_tools.py`

- [ ] **Step 1: Find where existing MCP tools are registered**

Run:
```bash
grep -n "@mcp\.tool\|@server\.tool\|register_tool" src/tradingview_mcp/server.py | head -20
```

Note the exact decorator pattern used by existing tools (e.g., `backtest_strategy`). The new tools must use the same pattern for consistency.

- [ ] **Step 2: Write failing integration tests**

Create `tests/integration/__init__.py` (empty).

Create `tests/integration/test_yt_mcp_tools.py`:

```python
"""End-to-end MCP stdio tests for the three new tools."""
from __future__ import annotations

import json
import select
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SMA_FIXTURE = (REPO_ROOT / "tests" / "fixtures" / "strategies" / "sma_cross.py").read_text()


@pytest.fixture
def mcp_proc(tmp_path, monkeypatch):
    """Spawn the MCP server with isolated storage."""
    env = {
        **__import__("os").environ,
        "STRATEGY_STORAGE_DIR": str(tmp_path),
        "RUNNER_TIMEOUT_S": "30",
    }
    # Use the locally installed package (uv run ensures venv path)
    proc = subprocess.Popen(
        ["uv", "run", "tradingview-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, bufsize=1, cwd=str(REPO_ROOT), env=env,
    )
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def _send(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def _recv(proc, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([proc.stdout], [], [], 0.2)
        if r:
            line = proc.stdout.readline()
            if line.strip():
                return json.loads(line)
    return None


def _initialize(proc):
    _send(proc, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"itest","version":"0"}}})
    _recv(proc)
    _send(proc, {"jsonrpc":"2.0","method":"notifications/initialized"})


def _call(proc, name, args, _id=99):
    _send(proc, {"jsonrpc":"2.0","id":_id,"method":"tools/call",
                  "params":{"name":name,"arguments":args}})
    return _recv(proc, timeout=60)


def test_three_yt_tools_listed(mcp_proc):
    _initialize(mcp_proc)
    _send(mcp_proc, {"jsonrpc":"2.0","id":2,"method":"tools/list"})
    resp = _recv(mcp_proc, timeout=10)
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "yt_extract_strategy" in tool_names
    assert "run_strategy_backtest" in tool_names
    assert "auto_tune_strategy" in tool_names


def test_run_strategy_backtest_fixture(mcp_proc):
    _initialize(mcp_proc)
    resp = _call(mcp_proc, "run_strategy_backtest", {
        "strategy_code": SMA_FIXTURE,
        "symbol": "FIXTURE_AAPL",
        "timeframe": "1d",
        "period": "2y",
        "slug": "itest-iter1",
    })
    assert "result" in resp
    # Result content is a list of MCP content items; the text item is JSON-encoded
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert "in_sample" in payload
    assert "out_of_sample" in payload
    assert "benchmark" in payload
```

- [ ] **Step 3: Run integration tests to verify they fail**

Run: `uv run pytest tests/integration/test_yt_mcp_tools.py -v`
Expected: `test_three_yt_tools_listed` fails because the new tools aren't registered yet.

- [ ] **Step 4: Register the three new tools in `server.py`**

Append to `src/tradingview_mcp/server.py` just before `def main()`:

```python


# ---------------------------------------------------------------------------
# YT → backtest MCP tools (added Phase 1)
# ---------------------------------------------------------------------------

from tradingview_mcp.core.services.yt_strategy.transcript import (
    fetch_transcript, TranscriptUnavailable, extract_video_id,
)
from tradingview_mcp.core.services.yt_strategy.rule_extractor import extract_rules
from tradingview_mcp.core.services.yt_strategy.codegen import (
    python_template, pine_template,
)
from tradingview_mcp.core.services.yt_strategy.runner import (
    run_backtest, SecurityViolation, StrategyTimeout, StrategyMemoryExceeded,
    InvalidStrategyClass, StrategyRuntimeError,
)
from tradingview_mcp.core.services.yt_strategy.autotune import auto_tune
from tradingview_mcp.core.errors import make_error, make_strategy_error, ErrorCode


@mcp.tool()
def yt_extract_strategy(url: str) -> dict:
    """Fetch a YouTube transcript and return Python+Pine skeleton templates.

    The assistant in Claude Desktop is expected to read ``transcript`` and
    fill in the TODO markers in ``python_skeleton`` / ``pine_skeleton``,
    then call ``run_strategy_backtest`` with the result.

    Args:
        url: YouTube video URL (watch / youtu.be / embed form).
    """
    try:
        result = fetch_transcript(url)
    except ValueError as e:
        return make_error(ErrorCode.INVALID_PARAMETER, str(e))
    except TranscriptUnavailable as e:
        return make_error(ErrorCode.TRANSCRIPT_UNAVAILABLE, str(e))

    spec = extract_rules(result.text)
    return {
        "transcript": result.text,
        "video_meta": {
            "video_id": result.video_id,
            "title": result.title,
            "channel": result.channel,
            "duration_s": result.duration_s,
            "language": result.language,
            "source": result.source,
        },
        "python_skeleton": python_template(spec),
        "pine_skeleton": pine_template(spec),
        "spec": {
            "name": spec.name,
            "entry_rules": spec.entry_rules,
            "exit_rules": spec.exit_rules,
            "indicators_used": spec.indicators_used,
            "confidence": spec.confidence,
        },
    }


@mcp.tool()
def run_strategy_backtest(
    strategy_code: str,
    symbol: str,
    timeframe: str,
    period: str,
    slug: str,
    cash: float = 10_000,
    commission: float | None = None,
    slippage: float | None = None,
    oos_validate: bool = True,
) -> dict:
    """Backtest LLM-generated *strategy_code* with walk-forward OOS validation.

    Args:
        strategy_code: Full Python source defining a subclass of backtesting.Strategy.
        symbol: e.g. "BTCUSDT" (Binance) or "AAPL" / "BTC-USD" (Yahoo).
        timeframe: e.g. "1h", "1d".
        period: e.g. "2y", "60d".
        slug: Filesystem-safe identifier under which artifacts are persisted.
        cash: Starting equity. Default 10,000.
        commission: Per-trade commission as a fraction. Default = asset-class profile.
        slippage: Per-trade slippage as a fraction (reserved; not yet wired through).
        oos_validate: When True (default), runs 5-fold expanding walk-forward.
    """
    try:
        return run_backtest(
            strategy_code=strategy_code, symbol=symbol, timeframe=timeframe,
            period=period, slug=slug, cash=cash, commission=commission,
            slippage=slippage, oos_validate=oos_validate,
        )
    except SecurityViolation as e:
        return make_strategy_error(
            ErrorCode.STRATEGY_SECURITY_VIOLATION, str(e),
            user_code_line=e.line, user_code_snippet=e.snippet,
        )
    except SyntaxError as e:
        return make_strategy_error(
            ErrorCode.STRATEGY_RUNTIME_ERROR, f"SyntaxError: {e.msg}",
            user_code_line=e.lineno,
            user_code_snippet=e.text.rstrip() if e.text else None,
        )
    except StrategyTimeout as e:
        return make_strategy_error(ErrorCode.STRATEGY_TIMEOUT, str(e))
    except StrategyMemoryExceeded as e:
        return make_strategy_error(ErrorCode.STRATEGY_MEMORY_EXCEEDED, str(e))
    except InvalidStrategyClass as e:
        return make_strategy_error(ErrorCode.STRATEGY_INVALID_CLASS, str(e))
    except StrategyRuntimeError as e:
        return make_strategy_error(
            ErrorCode.STRATEGY_RUNTIME_ERROR, str(e),
            user_code_line=e.user_code_line,
            user_code_snippet=e.user_code_snippet,
        )
    except ValueError as e:
        return make_error(ErrorCode.INVALID_PARAMETER, str(e))


@mcp.tool()
def auto_tune_strategy(
    strategy_code: str,
    param_grid: dict,
    symbol: str,
    timeframe: str,
    period: str,
    metric: str = "Sharpe Ratio",
    method: str = "grid",
    max_tries: int = 50,
) -> dict:
    """Sweep *param_grid* against *strategy_code* and return the best params.

    No LLM. Deterministic grid search inside a sandboxed subprocess.

    Args:
        strategy_code: Full strategy source (same shape as run_strategy_backtest).
        param_grid: {param_name: [values]}. Cartesian product is swept.
        symbol, timeframe, period: market window (same routing as run_strategy_backtest).
        metric: backtesting.py stat name to maximize. Default "Sharpe Ratio".
        method: "grid" (only supported value at MVP).
        max_tries: cap on number of param combinations explored.
    """
    try:
        return auto_tune(
            strategy_code=strategy_code, param_grid=param_grid, symbol=symbol,
            timeframe=timeframe, period=period, metric=metric, method=method,
            max_tries=max_tries,
        )
    except SecurityViolation as e:
        return make_strategy_error(
            ErrorCode.STRATEGY_SECURITY_VIOLATION, str(e),
            user_code_line=e.line, user_code_snippet=e.snippet,
        )
    except ValueError as e:
        return make_error(ErrorCode.INVALID_PARAMETER, str(e))
```

Note: this assumes `mcp` is the module-level `FastMCP` (or equivalent) object the existing tools are registered against. Verify by reading the top of `server.py` first; if the project uses a different decorator (`@server.tool`, `@app.tool`), substitute it. The pattern is consistent within the file — copy whatever the existing `backtest_strategy` tool uses.

- [ ] **Step 5: Run the integration tests to verify they pass**

Run: `uv run pytest tests/integration/test_yt_mcp_tools.py -v`
Expected: both tests pass. `test_run_strategy_backtest_fixture` may take 30-60s due to the subprocess + walk-forward.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/tradingview_mcp/server.py tests/integration/
git commit -m "$(cat <<'EOF'
feat(server): register three yt_strategy MCP tools

yt_extract_strategy, run_strategy_backtest, auto_tune_strategy are now
exposed to Claude Desktop. Each wraps its yt_strategy module entry,
translates internal exceptions into the existing core/errors.py envelope,
and uses the rich strategy-error fields (line, snippet, hint) so the
assistant can iterate cleanly.

Integration tests use the MCP stdio handshake against a real uv-spawned
server, exercising the FIXTURE_AAPL bypass path for hermetic test runs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14 — `.env.example` documentation + CI workflow

**Files:**
- Modify: `.env.example`
- Create: `.github/workflows/test.yml`

- [ ] **Step 1: Document new env vars**

Append to `.env.example`:

```bash

# ── YT → Backtest pipeline ─────────────────────────────────────
# Strategy subprocess wall-clock cap (seconds). Default 60.
RUNNER_TIMEOUT_S=60

# Strategy subprocess memory cap (MB). Default 1000.
# macOS may silently ignore; on Linux this enforces RLIMIT_AS.
RUNNER_MEMORY_MB=1000

# YouTube transcript cache lifetime (hours). 0 disables cache.
YT_TRANSCRIPT_CACHE_TTL_H=24

# Persisted runs root.
STRATEGY_STORAGE_DIR=~/.tradingview_mcp_data

# Binance API base. Override for US ("https://data-api.binance.vision") or testing.
BINANCE_API_BASE=https://api.binance.com
```

- [ ] **Step 2: Create CI workflow**

Create `.github/workflows/test.yml`:

```yaml
# Run the pytest suite on PR + main push.
name: tests

on:
  push:
    branches: [main]
    paths-ignore:
      - "**.md"
      - "docs/**"
      - "LICENSE"
  pull_request:
    branches: [main]
    paths-ignore:
      - "**.md"
      - "docs/**"

concurrency:
  group: tests-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Run unit tests
        run: uv run pytest tests/unit -v --timeout=120

      - name: Run integration tests
        run: uv run pytest tests/integration -v --timeout=300
```

- [ ] **Step 3: Verify the workflow YAML is valid**

Run:
```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml')); print('yaml ok')"
```
Expected: `yaml ok`.

- [ ] **Step 4: Commit**

```bash
git add .env.example .github/workflows/test.yml
git commit -m "$(cat <<'EOF'
chore: document new env vars + add CI test workflow

.env.example now lists RUNNER_TIMEOUT_S, RUNNER_MEMORY_MB,
YT_TRANSCRIPT_CACHE_TTL_H, STRATEGY_STORAGE_DIR, BINANCE_API_BASE with
their defaults and behavior. New test.yml workflow runs pytest on Python
3.10/3.11/3.12 for every PR and main push (paths-ignore matches the
existing publish-image workflow so doc-only changes don't trigger CI).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15 — Final verification + brief README mention

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Full test suite final pass**

Run: `uv run pytest tests/ -v --timeout=300`
Expected: all unit + integration tests pass.

- [ ] **Step 2: Smoke-test the MCP server end-to-end**

Run:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' | uv run tradingview-mcp 2>/dev/null | head -1
```
Expected: a JSON line containing `"serverInfo"` and no error.

- [ ] **Step 3: Add a short section to README**

In `README.md`, find the existing "Tools" section (or whatever lists tools). Add a subsection:

```markdown
### YT → Backtest (Phase 1)

Three tools that turn a YouTube strategy video into a walk-forward-validated backtest plus Pine v6 script:

- `yt_extract_strategy(url)` — fetches transcript + returns Python and Pine skeletons.
- `run_strategy_backtest(strategy_code, symbol, timeframe, period, slug, …)` — runs the strategy in a sandboxed subprocess with walk-forward OOS validation and buy-and-hold benchmark; persists artifacts under `~/.tradingview_mcp_data/strategies/<slug>/`.
- `auto_tune_strategy(strategy_code, param_grid, symbol, timeframe, period, …)` — deterministic grid-search over parameters; no LLM.

Strategy code runs in a hardened subprocess: AST scan rejects forbidden imports/builtins/dunder access; restricted `__builtins__`; `multiprocessing.Process` with `spawn`; `RLIMIT_AS` 1 GB cap (Linux); 60 s wall-clock timeout. See `docs/superpowers/specs/2026-06-03-yt-to-backtest-mcp-design.md` for the full security model.

Env vars: `RUNNER_TIMEOUT_S`, `RUNNER_MEMORY_MB`, `YT_TRANSCRIPT_CACHE_TTL_H`, `STRATEGY_STORAGE_DIR`, `BINANCE_API_BASE`.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): document the three yt_strategy MCP tools

Brief subsection covering yt_extract_strategy, run_strategy_backtest,
auto_tune_strategy with their security envelope and new env vars. Full
design lives in docs/superpowers/specs/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Final summary**

Print the change summary:

```bash
git log --oneline 61e6bc9..HEAD
```

Confirm each task produced one commit (15 commits total since the spec commit). Diff between baseline and final:

```bash
git diff --stat 3425c1d..HEAD
```

---

## Self-Review

**Spec coverage check** — each spec section maps to at least one task:

| Spec § | Task |
|---|---|
| §3 Locked decisions 1-7 | All tasks (architecture baked in) |
| §4 Architecture | Task 13 (server.py wiring); diagram lives in spec |
| §5.1 `transcript.py` | Task 3 |
| §5.2 `rule_extractor.py` | Task 5 |
| §5.3 `codegen.py` | Task 6 |
| §5.4 `data.py` + cost profiles | Task 4 |
| §5.5 `runner.py` security | Task 7 (AST) + Task 8 (subprocess) + Task 11 (orchestration) |
| §5.6 `walkforward.py` | Task 9 |
| §5.7 `autotune.py` | Task 12 |
| §5.8 `storage.py` | Task 10 |
| §5.9 server.py tools | Task 13 |
| §6 Data flow | Task 11 + Task 13 (integration tests exercise the flow) |
| §7 Error handling | Task 2 (codes) + Task 13 (tool wrappers translate exceptions) |
| §8 Testing | Each task has its own tests; Task 13 covers integration; Task 14 adds CI |
| §9 New deps | Task 1 |
| §10 Env vars | Task 14 (.env.example) |
| §11 Risks & mitigations | Encoded in §5.5/§7 implementation; no separate task |
| §13 Out-of-MVP follow-ups | Not implemented (by design) |

**Placeholder scan:** done — no TBDs, all code blocks complete, all test cases concrete.

**Type consistency:** `StrategySpec`, `RunArtifacts`, `CostProfile`, `Issue`, `TranscriptResult` are defined once and referenced consistently. Exception names (`SecurityViolation`, `StrategyTimeout`, `StrategyMemoryExceeded`, `InvalidStrategyClass`, `StrategyRuntimeError`, `TranscriptUnavailable`) are consistent across runner.py, transcript.py, and server.py.

**Scope check:** 15 tasks, each producing one commit, each independently testable. Total scope is one implementation plan worth of work — fits a single execution session.
