"""Security tests for the runner's AST scanner.

Every malicious sample MUST be rejected; every benign sample MUST pass.
A failure here is a sandbox regression - treat as a P0.
"""
from __future__ import annotations

import sys
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
    ("__builtins__['eval']('1')",                        "__builtins__"),
    ("import builtins",                                  "builtins"),
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
    scan_strategy_code(code)  # must not raise


def test_self_data_close_access_allowed():
    safe = """
from backtesting import Strategy
class S(Strategy):
    def init(self): pass
    def next(self):
        x = self.data.Close[-1]
"""
    scan_strategy_code(safe)


def test_arbitrary_dict_access_blocked():
    """__dict__ on anything other than self.data must be rejected."""
    bad = """
from backtesting import Strategy
class S(Strategy):
    def init(self): pass
    def next(self):
        leaked = type.__dict__
"""
    with pytest.raises(SecurityViolation) as exc_info:
        scan_strategy_code(bad)
    assert "__dict__" in str(exc_info.value)


def test_self_data_dict_access_allowed():
    """self.data.__dict__ is the documented carve-out and must be allowed."""
    safe = """
from backtesting import Strategy
class S(Strategy):
    def init(self): pass
    def next(self):
        d = self.data.__dict__
"""
    scan_strategy_code(safe)  # must not raise


# --- subprocess exec tests ---

from tradingview_mcp.core.services.yt_strategy.runner import (
    StrategyTimeout,
    StrategyMemoryExceeded,
    InvalidStrategyClass,
    exec_strategy_in_subprocess,
)
import pandas as pd

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


@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="RLIMIT_AS is not enforced on macOS; memory cap depends on Linux. "
           "Test passes on the Linux CI runner.",
)
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
