"""End-to-end MCP stdio tests for the three new yt_strategy tools."""
from __future__ import annotations

import json
import os
import select
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SMA_FIXTURE = (REPO_ROOT / "tests" / "fixtures" / "strategies" / "sma_cross.py").read_text()


@pytest.fixture
def mcp_proc(tmp_path):
    """Spawn the MCP server with isolated storage."""
    env = {
        **os.environ,
        "STRATEGY_STORAGE_DIR": str(tmp_path),
        "RUNNER_TIMEOUT_S": "30",
    }
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
    return _recv(proc, timeout=120)


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
    # Result content is a list of MCP content items; the text item is JSON-encoded.
    text = resp["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert "in_sample" in payload
    assert "out_of_sample" in payload
    assert "benchmark" in payload
