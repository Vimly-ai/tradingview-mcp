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
CHART_READY            = '[data-name="legend-source-item"]'
PINE_EDITOR_READY      = 'div.tv-script-editor'
STRATEGY_TESTER_READY  = '[data-name="strategy-tester-overview"]'


# --- Login state -------------------------------------------------------------
LOGGED_IN_INDICATOR    = 'button[aria-label="Open user menu"]'


# --- Chart -------------------------------------------------------------------
MAIN_CHART_CANVAS               = 'div[data-name="pane-main"] canvas'
TICKER_SEARCH_INPUT             = 'input[data-role="search-input"]'
INDICATOR_DIALOG_OPEN_BTN       = 'button[data-name="open-indicators"]'
INDICATOR_SEARCH_DIALOG_INPUT   = 'input[data-name="indicator-search"]'
INDICATOR_DIALOG_FIRST_RESULT   = 'div[data-name="indicator-result"]:first-child'


# --- Pine Editor -------------------------------------------------------------
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
