"""End-to-end MCP stdio test — confirms all 17 tools are registered."""
from __future__ import annotations

import json
import os
import select
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def mcp_proc(tmp_path):
    env = {
        **os.environ,
        "STRATEGY_STORAGE_DIR": str(tmp_path),
        "TV_BROWSER_USER_DATA_DIR": str(tmp_path / "browser"),
        "TV_BROWSER_HEADLESS": "true",
    }
    proc = subprocess.Popen(
        ["uv", "run", "tradingview-mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, cwd=str(REPO_ROOT), env=env,
    )
    yield proc
    proc.terminate()
    try: proc.wait(timeout=3)
    except subprocess.TimeoutExpired: proc.kill()


def _send(p, obj):
    p.stdin.write(json.dumps(obj) + "\n"); p.stdin.flush()


def _recv(p, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([p.stdout], [], [], 0.2)
        if r:
            line = p.stdout.readline()
            if line.strip(): return json.loads(line)
    return None


def test_seventeen_tv_tools_are_registered(mcp_proc):
    _send(mcp_proc, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"itest","version":"0"}}})
    _recv(mcp_proc)
    _send(mcp_proc, {"jsonrpc":"2.0","method":"notifications/initialized"})

    _send(mcp_proc, {"jsonrpc":"2.0","id":2,"method":"tools/list"})
    resp = _recv(mcp_proc, timeout=10)
    names = {t["name"] for t in resp["result"]["tools"]}

    expected = {
        "tv_login_status", "tv_open_login_prompt", "tv_logout", "tv_close_browser",
        "tv_open_chart", "tv_screenshot_chart", "tv_add_indicator",
        "tv_read_watchlist", "tv_read_alerts", "tv_list_my_indicators",
        "tv_paste_pine", "tv_save_indicator", "tv_run_strategy_tester",
        "tv_create_alert", "tv_delete_alert",
        "tv_add_to_watchlist", "tv_remove_from_watchlist",
    }
    missing = expected - names
    assert not missing, f"Missing tv_* tools: {missing}"
