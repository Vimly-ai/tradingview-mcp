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
    page.url = ""
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
    page.click.assert_not_called()


async def test_paste_pine_succeeds_with_clean_code(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    page = _page()
    result = await paste_pine(page, code="//@version=6\nindicator('x')", name="test", save=True)
    assert result["saved"] is True
    assert result["name"] == "test"
    assert any("save" in str(call) for call in page.click.call_args_list)


async def test_paste_pine_loads_from_slug(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
    strategies = tmp_path / "strategies" / "BTCUSDT-1h-iter2"
    strategies.mkdir(parents=True)
    (strategies / "strategy.pine").write_text("//@version=6\nstrategy('X')")
    page = _page()
    result = await paste_pine(page, slug="BTCUSDT-1h-iter2")
    assert result["slug"] == "BTCUSDT-1h-iter2"


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
