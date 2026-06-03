"""Python + Pine v6 templates and Pine structural validator."""
from __future__ import annotations

from dataclasses import dataclass

from .rule_extractor import StrategySpec


@dataclass
class Issue:
    """One structural problem found by a validator."""
    severity: str  # "error" | "warning"
    message: str
    line: int | None = None


_PYTHON_TEMPLATE = '''"""LLM-generated trading strategy.

This is a skeleton. The assistant fills in the indicators_used in init()
and the entry/exit logic in next(). Only `backtesting`, `pandas as pd`,
`numpy as np`, `ta`, `math`, and `statistics` are available — anything
else will be rejected by the runner's AST scan.
"""
from backtesting import Strategy
from backtesting.lib import crossover

import pandas as pd
import numpy as np
import ta


class {class_name}(Strategy):
    # TODO: add tunable params here as class attributes (e.g. rsi_period = 14)

    def init(self):
        # TODO: precompute indicators with self.I(...)
        # Example: self.rsi = self.I(ta.momentum.RSIIndicator,
        #                            pd.Series(self.data.Close), self.rsi_period).rsi
        pass

    def next(self):
        # TODO: entry/exit logic. self.position, self.buy(), self.sell(), self.position.close()
        pass
'''


def python_template(spec: StrategySpec) -> str:
    """Return a backtesting.py Strategy skeleton for *spec*."""
    name = (spec.name or "Strategy").strip() or "Strategy"
    safe_name = "".join(c if c.isalnum() else "_" for c in name) or "Strategy"
    class_name = f"Strategy_{safe_name}"
    return _PYTHON_TEMPLATE.format(class_name=class_name)


_PINE_TEMPLATE = '''//@version=6
strategy("{title}", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100, commission_type=strategy.commission.percent, commission_value=0.1)

// TODO: parameters (input.int / input.float)
// rsi_period = input.int(14, "RSI period")

// TODO: indicators
// rsi = ta.rsi(close, rsi_period)

// TODO: entry/exit
// if (rsi < 30)
//     strategy.entry("long", strategy.long)
// if (rsi > 70)
//     strategy.close("long")
'''


def pine_template(spec: StrategySpec) -> str:
    """Return a Pine v6 strategy skeleton for *spec*."""
    title = (spec.name or "Strategy").strip().replace('"', "'") or "Strategy"
    return _PINE_TEMPLATE.format(title=title)


def validate_pine(code: str) -> list[Issue]:
    """Structurally validate Pine v6 code.

    Catches the small set of mistakes most likely from LLM output:
    missing ``//@version=6``, no ``strategy()``/``indicator()`` call,
    unbalanced parens. Not a full parser; not a runtime check.
    """
    issues: list[Issue] = []

    if "//@version=6" not in code and "//@version=5" not in code:
        issues.append(Issue("error", "Missing Pine version directive (//@version=6)."))

    has_strategy = "strategy(" in code
    has_indicator = "indicator(" in code
    has_library = "library(" in code
    if not (has_strategy or has_indicator or has_library):
        issues.append(Issue(
            "error",
            "Pine must contain exactly one of: strategy(), indicator(), library().",
        ))

    # Parenthesis balance (ignoring content inside string literals).
    depth = 0
    in_str: str | None = None
    for ch in code:
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                issues.append(Issue("error", "Unbalanced parens: closer without opener."))
                break
    if depth > 0:
        issues.append(Issue("error", f"Unbalanced parens: {depth} unclosed."))

    return issues
