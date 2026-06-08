"""Two-keys-in-two-pockets baseline check."""
from __future__ import annotations

import pytest

from tradingview_mcp.core.services.tv_browser import selectors


EXPECTED_SELECTORS = {
    "CHART_READY":            '[data-name="legend-source-item"]',
    "PINE_EDITOR_READY":      'div.tv-script-editor',
    "STRATEGY_TESTER_READY":  '[data-name="strategy-tester-overview"]',
    "LOGGED_IN_INDICATOR":    'button[aria-label="Open user menu"]',
    "MAIN_CHART_CANVAS":      'div[data-name="pane-main"] canvas',
    "TICKER_SEARCH_INPUT":    'input[data-role="search-input"]',
    "INDICATOR_DIALOG_OPEN_BTN":     'button[data-name="open-indicators"]',
    "INDICATOR_SEARCH_DIALOG_INPUT": 'input[data-name="indicator-search"]',
    "INDICATOR_DIALOG_FIRST_RESULT": 'div[data-name="indicator-result"]:first-child',
    "PINE_EDITOR_TEXTAREA":           'div.monaco-editor',
    "PINE_EDITOR_SAVE_BTN":           'button[data-name="save"]',
    "PINE_EDITOR_ADD_TO_CHART_BTN":   'button[data-name="add-to-chart"]',
    "PINE_EDITOR_ERROR_PANEL":        'div[data-name="pine-script-errors"]',
    "PINE_EDITOR_TAB":                'button[data-name="open-pine-editor"]',
    "SAVE_DIALOG_NAME_INPUT":         'input[data-name="script-name"]',
    "SAVE_DIALOG_CONFIRM_BTN":        'button[data-name="save-confirm"]',
    "STRATEGY_TESTER_TAB":            'button[id="footer-tester"]',
    "STRATEGY_TESTER_STATS_PANEL":    'div[data-name="strategy-tester-stats"]',
    "STRATEGY_TESTER_REPORT_REGION":  'div[data-name="strategy-tester-report"]',
    "WATCHLIST_ROWS":                 '[data-name="watchlist-symbol-row"]',
    "WATCHLIST_DROPDOWN":             'button[data-name="watchlist-selector"]',
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
