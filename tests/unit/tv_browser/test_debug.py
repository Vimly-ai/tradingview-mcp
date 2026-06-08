from __future__ import annotations

import os
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
    for i in range(25):
        d = root / f"2026-06-07T{i:02d}-00-00-foo"
        d.mkdir()
        (d / "x.txt").write_text("x")
        os_time = time.time() - (25 - i)
        os.utime(d, (os_time, os_time))

    rotate_artifacts(root, max_count=10)
    remaining = sorted(root.iterdir())
    assert len(remaining) == 10
