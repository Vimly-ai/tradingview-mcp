"""Security tests for the runner's AST scanner.

Every malicious sample MUST be rejected; every benign sample MUST pass.
A failure here is a sandbox regression - treat as a P0.
"""
from __future__ import annotations

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
