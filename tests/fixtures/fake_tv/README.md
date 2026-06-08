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
