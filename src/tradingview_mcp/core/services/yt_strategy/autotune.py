"""Deterministic parameter optimization for a fixed strategy structure.

No LLM. Wraps backtesting.py's Backtest with grid search; same security
envelope as runner (AST scan, subprocess, RLIMIT, timeout, FD hygiene).
"""
from __future__ import annotations

import itertools
import multiprocessing as _mp
import os
import pickle as _pickle
from typing import Any

from .data import fetch_ohlcv, cost_profile_for
from .runner import scan_strategy_code, _safe_builtins


def _tune_in_subprocess(strategy_code: str, df_pickle: bytes, param_grid: dict, metric: str,
                         cash: float, commission: float, seed: int, conn) -> None:
    """Child process for tuning."""
    import resource
    try:
        mb = int(os.environ.get("RUNNER_MEMORY_MB", "1500"))
        resource.setrlimit(resource.RLIMIT_AS, (mb * 1024 * 1024, mb * 1024 * 1024))
    except (ValueError, OSError):
        pass

    try:
        df = _pickle.loads(df_pickle)
        sandbox_globals: dict[str, Any] = {"__builtins__": _safe_builtins()}
        exec(compile(strategy_code, "<strategy>", "exec"), sandbox_globals)

        from backtesting import Backtest, Strategy
        strategy_cls = None
        for v in sandbox_globals.values():
            if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy:
                strategy_cls = v
                break
        if strategy_cls is None:
            conn.send(("invalid_class", None)); return

        bt = Backtest(df, strategy_cls, cash=cash, commission=commission)
        keys = sorted(param_grid.keys())
        combos = list(itertools.product(*(param_grid[k] for k in keys)))
        trials = []
        best_metric = float("-inf")
        best_params: dict | None = None
        for combo in combos:
            params = dict(zip(keys, combo))
            try:
                stats = bt.run(**params)
                m = float(stats.get(metric, 0) or 0)
            except Exception:
                m = float("-inf")
            trials.append({"params": params, "metric": m})
            if m > best_metric:
                best_metric = m
                best_params = params
        trials.sort(key=lambda t: t["metric"], reverse=True)
        conn.send(("ok", {"best_params": best_params, "best_metric": best_metric, "all_trials": trials}))
    except Exception as e:
        conn.send(("error", {"message": str(e)}))
    finally:
        conn.close()


def auto_tune(
    strategy_code: str,
    param_grid: dict[str, list],
    symbol: str,
    timeframe: str,
    period: str,
    metric: str = "Sharpe Ratio",
    method: str = "grid",
    max_tries: int = 50,
    seed: int = 42,
    cash: float = 10_000,
    commission: float | None = None,
) -> dict[str, Any]:
    """Grid-search *param_grid* against the strategy in *strategy_code*.

    Parameters
    ----------
    strategy_code:
        Python source defining a backtesting.Strategy subclass.
    param_grid:
        Mapping of parameter name -> list of candidate values.
        All combinations are tried in lexicographic key order (deterministic).
    symbol:
        Ticker symbol; ``FIXTURE_*`` symbols load synthetic test data.
    timeframe:
        Bar interval (e.g. ``"1d"``).
    period:
        Lookback period (e.g. ``"2y"``).
    metric:
        backtesting.py stats key to maximise (default: ``"Sharpe Ratio"``).
    method:
        ``"grid"`` (only supported value; ``skopt`` Bayesian reserved).
    max_tries:
        Maximum number of combos to evaluate (grid is truncated after this).
    seed:
        Unused by pure grid search but accepted for API stability.
    cash:
        Starting capital.
    commission:
        Override commission fraction; defaults to symbol cost profile.

    Returns
    -------
    dict with keys ``best_params``, ``best_metric``, ``metric_name``,
    ``all_trials`` (sorted descending by metric).
    """
    scan_strategy_code(strategy_code)
    profile = cost_profile_for(symbol)
    commission_used = commission if commission is not None else profile.commission

    df = fetch_ohlcv(symbol, timeframe, period)
    df_pickle = _pickle.dumps(df)

    ctx = _mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_tune_in_subprocess,
        args=(strategy_code, df_pickle, param_grid, metric, cash, commission_used, seed, child_conn),
    )
    proc.start()
    child_conn.close()  # parent doesn't need the child end

    per_trial_s = float(os.environ.get("RUNNER_TIMEOUT_S", "60"))
    n_combos = 1
    for v in param_grid.values():
        n_combos *= len(v)
    proc.join(timeout=per_trial_s * min(n_combos, max_tries) + 30)
    if proc.is_alive():
        proc.kill(); proc.join(timeout=2)
        parent_conn.close()
        raise TimeoutError("auto_tune exceeded budget.")

    try:
        if not parent_conn.poll():
            raise RuntimeError("auto_tune subprocess produced no result.")
        tag, payload = parent_conn.recv()
        if tag != "ok":
            raise RuntimeError(f"auto_tune failed: {payload}")
        payload["metric_name"] = metric
        return payload
    finally:
        parent_conn.close()
