from __future__ import annotations

import ast

import pytest

from tradingview_mcp.core.services.yt_strategy.rule_extractor import StrategySpec
from tradingview_mcp.core.services.yt_strategy.codegen import (
    Issue,
    python_template,
    pine_template,
    validate_pine,
)


class TestPythonTemplate:
    def test_returns_valid_python(self):
        code = python_template(StrategySpec(name="TestStrat"))
        ast.parse(code)

    def test_defines_strategy_subclass(self):
        code = python_template(StrategySpec(name="TestStrat"))
        assert "class" in code
        assert "Strategy" in code
        assert "def init" in code
        assert "def next" in code

    def test_includes_todo_markers(self):
        code = python_template(StrategySpec(name="TestStrat"))
        assert "TODO" in code

    def test_imports_safe_namespace_only(self):
        code = python_template(StrategySpec(name="TestStrat"))
        for forbidden in ("import os", "import subprocess", "import socket", "open("):
            assert forbidden not in code


class TestPineTemplate:
    def test_has_version_directive(self):
        code = pine_template(StrategySpec(name="TestStrat"))
        assert "//@version=6" in code

    def test_has_strategy_call(self):
        code = pine_template(StrategySpec(name="TestStrat"))
        assert "strategy(" in code

    def test_includes_todo_markers(self):
        code = pine_template(StrategySpec(name="TestStrat"))
        assert "TODO" in code


class TestValidatePine:
    def test_valid_pine_returns_empty(self):
        good = '//@version=6\nstrategy("X", overlay=true)\nplot(close)\n'
        assert validate_pine(good) == []

    def test_missing_version_flagged(self):
        bad = 'strategy("X", overlay=true)\nplot(close)\n'
        issues = validate_pine(bad)
        assert any("version" in i.message.lower() for i in issues)

    def test_missing_strategy_or_indicator_flagged(self):
        bad = '//@version=6\nplot(close)\n'
        issues = validate_pine(bad)
        assert any("strategy" in i.message.lower() or "indicator" in i.message.lower() for i in issues)

    def test_unbalanced_parens_flagged(self):
        bad = '//@version=6\nstrategy("X", overlay=true\nplot(close)\n'
        issues = validate_pine(bad)
        assert any("paren" in i.message.lower() or "balance" in i.message.lower() for i in issues)
