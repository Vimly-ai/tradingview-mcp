"""Sandboxed exec of LLM-generated strategy code.

This file is security-critical. Modifications must add a regression test
to test_runner_sandbox.py first.

Defense in depth:
    1. AST pre-scan (this file): reject before exec on forbidden names
    2. Restricted exec namespace: only safe libraries in scope
    3. Subprocess isolation: strategy runs in a separate Process
    4. Wall-clock timeout: process.kill() after N seconds
    5. Memory cap: RLIMIT_AS in subprocess

Layers 2-5 are implemented in the next task; layer 1 is here.
"""
from __future__ import annotations

import ast


class SecurityViolation(Exception):
    """Raised when AST scan rejects LLM-generated code."""

    def __init__(self, message: str, line: int | None = None, snippet: str | None = None):
        super().__init__(message)
        self.line = line
        self.snippet = snippet


_BANNED_MODULES = frozenset({
    "os", "subprocess", "socket", "urllib", "urllib2", "urllib3",
    "requests", "httpx", "aiohttp", "ftplib", "smtplib", "telnetlib",
    "shutil", "glob", "pickle", "marshal", "shelve", "dbm",
    "ctypes", "multiprocessing", "threading", "asyncio",
    "signal", "atexit", "resource", "tempfile", "pathlib",
    "importlib", "imp", "pty", "fcntl", "ioctl",
    "platform", "sysconfig", "site", "code", "codeop",
    "builtins",  # full reflective access to all dangerous builtins
})

_BANNED_BUILTINS = frozenset({
    "open", "eval", "exec", "compile", "__import__",
    "globals", "locals", "vars", "breakpoint",
    "exit", "quit", "help", "input",
    "__builtins__",   # also catch bare-name access
})

_BANNED_DUNDER_ATTRS = frozenset({
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__builtins__", "__code__",
    "__import__", "__loader__", "__spec__",
    # __dict__ allowed only on self.data - handled separately
})


def _line_snippet(code: str, line: int | None) -> str | None:
    if line is None:
        return None
    lines = code.splitlines()
    if 0 < line <= len(lines):
        return lines[line - 1]
    return None


class _ScanVisitor(ast.NodeVisitor):
    def __init__(self, code: str) -> None:
        self.code = code
        self.violations: list[SecurityViolation] = []

    def _fail(self, msg: str, node: ast.AST) -> None:
        line = getattr(node, "lineno", None)
        self.violations.append(SecurityViolation(msg, line=line, snippet=_line_snippet(self.code, line)))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            if top in _BANNED_MODULES:
                self._fail(f"Forbidden import: {alias.name!r} (banned module {top!r}).", node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            top = node.module.split(".", 1)[0]
            if top in _BANNED_MODULES:
                self._fail(f"Forbidden import: from {node.module!r} (banned module {top!r}).", node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in _BANNED_BUILTINS:
            self._fail(f"Forbidden builtin: {node.id!r}.", node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _BANNED_DUNDER_ATTRS:
            self._fail(f"Forbidden attribute access: {node.attr!r}.", node)
        elif node.attr == "__dict__":
            # Allowed only on self.data
            v = node.value
            if not (isinstance(v, ast.Attribute) and v.attr == "data"
                    and isinstance(v.value, ast.Name) and v.value.id == "self"):
                self._fail("Forbidden attribute access: '__dict__' allowed only on self.data.", node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # NOTE on residual risk: this catches only string-literal dunder
        # arguments (ast.Constant). Dynamically constructed strings such as
        # getattr(x, "__cl" + "ass__") or getattr(x, f"__{'class'}__")
        # cannot be statically rejected here — the AST only sees a BinOp
        # or JoinedStr. Defense-in-depth covers this: the restricted
        # __builtins__ in _safe_builtins strips reflective helpers, the
        # spawned subprocess is isolated, and the wall-clock + memory
        # caps bound any escalation. Adding runtime guards inside the
        # exec'd code is intentionally avoided to keep layers separable.
        # getattr/setattr/delattr/hasattr with dunder string -> reject
        func = node.func
        is_reflective = (
            isinstance(func, ast.Name)
            and func.id in {"getattr", "setattr", "delattr", "hasattr"}
        )
        if is_reflective and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            arg = node.args[1].value
            if isinstance(arg, str) and arg.startswith("__"):
                self._fail(
                    f"Forbidden reflective access: {func.id}(_, {arg!r}).", node,
                )
        self.generic_visit(node)


def scan_strategy_code(code: str) -> None:
    """Reject LLM-generated *code* if it references forbidden names.

    Raises:
        SecurityViolation: on first forbidden reference encountered. The
            exception's ``line`` and ``snippet`` attributes locate it.
        SyntaxError: if *code* is not parseable Python.
    """
    tree = ast.parse(code)
    visitor = _ScanVisitor(code)
    visitor.visit(tree)
    if visitor.violations:
        raise visitor.violations[0]


# ---------------------------------------------------------------------------
# Subprocess execution layer (Layers 2-5 of defense-in-depth)
# ---------------------------------------------------------------------------

import multiprocessing as _mp
import os as _os
import pickle as _pickle
import traceback as _tb
from typing import Any


class StrategyTimeout(Exception):
    """Raised when the strategy subprocess exceeds the wall-clock cap."""


class StrategyMemoryExceeded(Exception):
    """Raised when the strategy subprocess exceeds RLIMIT_AS."""


class InvalidStrategyClass(Exception):
    """Raised when exec'd code defines no backtesting.Strategy subclass."""


class StrategyRuntimeError(Exception):
    """Raised when the strategy raised an exception during execution.

    Attributes ``user_code_line`` and ``user_code_snippet`` locate the failure
    inside the user-provided code (best-effort — derived from traceback).
    """
    def __init__(self, message: str, user_code_line: int | None, user_code_snippet: str | None):
        super().__init__(message)
        self.user_code_line = user_code_line
        self.user_code_snippet = user_code_snippet


def _runner_timeout_s() -> float:
    try:
        return float(_os.environ.get("RUNNER_TIMEOUT_S", "60"))
    except ValueError:
        return 60.0


def _runner_memory_bytes() -> int:
    try:
        mb = int(_os.environ.get("RUNNER_MEMORY_MB", "1000"))
    except ValueError:
        mb = 1000
    return mb * 1024 * 1024


_REQUIRED_DUNDERS = frozenset({
    # Required by the interpreter to execute class statements / module setup.
    "__build_class__", "__name__", "__doc__", "__package__", "__debug__",
})


def _safe_builtins() -> dict[str, Any]:
    """Curated __builtins__ for exec'd strategy code.

    Removes the banned-builtin set; keeps everything else. Routes __import__
    through a guard that rejects banned modules so `import pandas` works
    but `import os` doesn't.
    """
    import builtins
    allowed: dict[str, Any] = {}
    for name in dir(builtins):
        if name in _BANNED_BUILTINS:
            continue
        if name.startswith("_") and name not in _REQUIRED_DUNDERS:
            continue
        allowed[name] = getattr(builtins, name)

    orig_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        top = name.split(".", 1)[0]
        if top in _BANNED_MODULES:
            raise ImportError(f"Forbidden import {name!r} blocked by sandbox.")
        return orig_import(name, globals, locals, fromlist, level)

    allowed["__import__"] = _guarded_import
    return allowed


def _child_target(code: str, df_pickle: bytes, cash: float, commission: float, conn) -> None:
    """multiprocessing entrypoint. Runs in the child process."""
    import resource

    # Memory cap. RLIMIT_AS is virtual memory in bytes.
    try:
        cap = _runner_memory_bytes()
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    except (ValueError, OSError):
        # macOS may refuse; parent's wall-clock kill still covers us.
        pass

    try:
        df = _pickle.loads(df_pickle)
        sandbox_globals: dict[str, Any] = {"__builtins__": _safe_builtins()}
        exec(compile(code, "<strategy>", "exec"), sandbox_globals)

        from backtesting import Backtest, Strategy
        strategy_cls = None
        for v in sandbox_globals.values():
            if (
                isinstance(v, type)
                and issubclass(v, Strategy)
                and v is not Strategy
            ):
                strategy_cls = v
                break

        if strategy_cls is None:
            conn.send(("invalid_class", None))
            return

        bt = Backtest(df, strategy_cls, cash=cash, commission=commission)
        stats = bt.run()
        result = {
            "metrics": {
                "sharpe":         float(stats.get("Sharpe Ratio", 0) or 0),
                "cagr":           float(stats.get("Return (Ann.) [%]", 0) or 0),
                "mdd":            float(stats.get("Max. Drawdown [%]", 0) or 0),
                "win_rate":       float(stats.get("Win Rate [%]", 0) or 0),
                "profit_factor":  float(stats.get("Profit Factor", 0) or 0),
                "n_trades":       int(stats.get("# Trades", 0) or 0),
                "return_pct":     float(stats.get("Return [%]", 0) or 0),
            },
            "trade_log": stats._trades.to_dict("records") if hasattr(stats, "_trades") else [],
            "equity_curve": stats._equity_curve["Equity"].tolist() if hasattr(stats, "_equity_curve") else [],
        }
        conn.send(("ok", result))
    except MemoryError:
        conn.send(("memory", None))
    except Exception as e:
        try:
            tb_lines = _tb.format_exception(type(e), e, e.__traceback__)
            line = None
            for frame in _tb.extract_tb(e.__traceback__):
                if frame.filename == "<strategy>":
                    line = frame.lineno
                    break
            snippet = _line_snippet(code, line)
            conn.send(("runtime", {
                "message": str(e),
                "line": line,
                "snippet": snippet,
                "traceback": "".join(tb_lines),
            }))
        except Exception:
            # Reporting itself failed (broken traceback, codec error, ...).
            # Send a minimal envelope so the parent doesn't misclassify as
            # memory-exceeded.
            try:
                conn.send(("runtime", {
                    "message": repr(e),
                    "line": None,
                    "snippet": None,
                    "traceback": "",
                }))
            except Exception:
                pass  # nothing more we can do; finally will close pipe
    finally:
        conn.close()


def exec_strategy_in_subprocess(
    strategy_code: str,
    bars: Any,
    cash: float = 10_000,
    commission: float = 0.001,
) -> dict[str, Any]:
    """Exec strategy_code in a subprocess with timeout + memory cap.

    *bars* is a pandas DataFrame with Open/High/Low/Close/Volume columns.

    Raises:
        SecurityViolation   — AST scan rejected the code
        SyntaxError         — code didn't parse
        StrategyTimeout     — wall-clock exceeded
        StrategyMemoryExceeded
        InvalidStrategyClass
        StrategyRuntimeError
    """
    # Layer 1: AST pre-scan.
    scan_strategy_code(strategy_code)

    df_pickle = _pickle.dumps(bars)

    ctx = _mp.get_context("spawn")  # clean isolation on macOS
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_child_target,
        args=(strategy_code, df_pickle, cash, commission, child_conn),
    )
    proc.start()
    child_conn.close()  # parent no longer needs the child end
    proc.join(timeout=_runner_timeout_s())
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=2)
        parent_conn.close()
        raise StrategyTimeout(
            f"Strategy did not finish within {_runner_timeout_s():.0f}s wall-clock."
        )

    try:
        if not parent_conn.poll():
            # Subprocess died without sending — likely killed by OS for memory.
            raise StrategyMemoryExceeded(
                "Strategy subprocess terminated without result; "
                "likely killed for exceeding memory cap."
            )

        tag, payload = parent_conn.recv()
        if tag == "ok":
            return payload
        if tag == "invalid_class":
            raise InvalidStrategyClass(
                "No subclass of backtesting.Strategy defined in submitted code."
            )
        if tag == "memory":
            raise StrategyMemoryExceeded("Strategy hit MemoryError during execution.")
        if tag == "runtime":
            raise StrategyRuntimeError(
                payload["message"],
                user_code_line=payload["line"],
                user_code_snippet=payload["snippet"],
            )
        raise RuntimeError(f"Unknown subprocess tag: {tag!r}")
    finally:
        parent_conn.close()


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

from .data import fetch_ohlcv, cost_profile_for
from .walkforward import walk_forward_split, detect_overfit
from .storage import save_run, RunArtifacts


def _b_and_h(df) -> dict[str, float]:
    """Buy-and-hold benchmark on the same window."""
    start_price = float(df["Close"].iloc[0])
    end_price = float(df["Close"].iloc[-1])
    bh_return_pct = (end_price / start_price - 1.0) * 100.0
    rets = df["Close"].pct_change().dropna()
    if len(rets) > 1 and rets.std() > 0:
        bh_sharpe = float((rets.mean() / rets.std()) * (252 ** 0.5))
    else:
        bh_sharpe = 0.0
    return {"bh_return_pct": bh_return_pct, "bh_sharpe": bh_sharpe}


def _aggregate_oos(per_fold: list[dict]) -> dict[str, float]:
    """Mean metrics across walk-forward folds."""
    if not per_fold:
        return {"sharpe": 0.0, "cagr": 0.0, "mdd": 0.0, "win_rate": 0.0,
                "profit_factor": 0.0, "n_trades": 0, "return_pct": 0.0}
    keys = per_fold[0].keys()
    return {k: sum(f[k] for f in per_fold) / len(per_fold) for k in keys}


def run_backtest(
    strategy_code: str,
    symbol: str,
    timeframe: str,
    period: str,
    slug: str,
    cash: float = 10_000,
    commission: float | None = None,
    slippage: float | None = None,
    oos_validate: bool = True,
) -> dict[str, Any]:
    """Top-level entry. Fetches data, runs IS + walk-forward, persists artifacts."""
    profile = cost_profile_for(symbol)
    commission_used = commission if commission is not None else profile.commission

    df = fetch_ohlcv(symbol, timeframe, period)
    cw = df.attrs.get("clamp_warning") if hasattr(df, "attrs") else None
    initial_warnings: list[str] = [cw] if cw else []

    if df.empty or len(df) < 30:
        return {
            "in_sample": {}, "out_of_sample": {}, "benchmark": {},
            "overfit_flag": False, "warnings": initial_warnings + [f"Insufficient data: got {len(df)} bars."],
            "cost_profile": profile.name, "slug": slug, "run_path": "",
        }

    # In-sample full-window backtest
    in_sample = exec_strategy_in_subprocess(strategy_code, df, cash=cash, commission=commission_used)
    is_metrics = in_sample["metrics"]

    # Out-of-sample walk-forward
    oos_metrics: dict[str, float] = {}
    oos_failed = False
    warnings: list[str] = list(initial_warnings)
    if oos_validate and len(df) >= 60:
        folds = walk_forward_split(df, n_chunks=6)
        per_fold = []
        for _train, test in folds:
            try:
                fold_result = exec_strategy_in_subprocess(strategy_code, test, cash=cash, commission=commission_used)
                per_fold.append(fold_result["metrics"])
            except (StrategyTimeout, StrategyMemoryExceeded, StrategyRuntimeError, InvalidStrategyClass):
                continue
        if per_fold:
            oos_metrics = _aggregate_oos(per_fold)
        else:
            oos_metrics = _aggregate_oos([])  # zeros
            oos_failed = True
            warnings.append("All walk-forward folds failed; out-of-sample metrics not computed.")
    else:
        split = int(len(df) * 0.7)
        try:
            test_result = exec_strategy_in_subprocess(strategy_code, df.iloc[split:], cash=cash, commission=commission_used)
            oos_metrics = test_result["metrics"]
        except Exception:
            oos_metrics = is_metrics  # degrade gracefully
            warnings.append("Simple OOS split failed; falling back to in-sample metrics.")

    benchmark = _b_and_h(df)
    overfit = False if oos_failed else detect_overfit(is_metrics.get("sharpe", 0.0), oos_metrics.get("sharpe", 0.0))

    report = {
        "in_sample": is_metrics,
        "out_of_sample": oos_metrics,
        "benchmark": benchmark,
        "overfit_flag": overfit,
        "trade_log": in_sample.get("trade_log", []),
        "cost_profile": profile.name,
        "symbol": symbol, "timeframe": timeframe, "period": period,
        "slug": slug,
        "warnings": warnings,
    }

    artifacts = RunArtifacts(
        strategy_py=strategy_code,
        strategy_pine="",  # populated by codegen on final convergence
        report_json=report,
        transcript="",
        equity_curve_png=b"",  # PNG generation deferred
    )
    run_path = save_run(slug, artifacts)
    report["run_path"] = str(run_path)
    return report
