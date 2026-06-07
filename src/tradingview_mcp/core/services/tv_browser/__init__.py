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
