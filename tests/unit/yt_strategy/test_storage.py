from __future__ import annotations

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
