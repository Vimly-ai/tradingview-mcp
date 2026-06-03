"""Expanding-window walk-forward validation."""
from __future__ import annotations

import pandas as pd


def walk_forward_split(data: pd.DataFrame, n_chunks: int = 6) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Split *data* into ``n_chunks-1`` (train, test) folds with expanding train.

    For chunk index *k* in {1..n_chunks-1}, train is chunks 1..k, test is
    chunk k+1. Yields ``n_chunks-1`` folds total.

    Raises:
        ValueError: if data has fewer rows than n_chunks.
    """
    if len(data) < n_chunks:
        raise ValueError(f"Need at least {n_chunks} rows; got {len(data)}.")
    chunk_size = len(data) // n_chunks
    chunks = [data.iloc[i * chunk_size : (i + 1) * chunk_size] for i in range(n_chunks)]
    # Absorb any remainder rows into the last chunk so we don't drop them.
    if (n_chunks * chunk_size) < len(data):
        last_extra = data.iloc[n_chunks * chunk_size :]
        chunks[-1] = pd.concat([chunks[-1], last_extra])

    folds: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for k in range(1, n_chunks):
        train = pd.concat(chunks[:k])
        test = chunks[k]
        folds.append((train, test))
    return folds


def detect_overfit(is_sharpe: float, oos_sharpe: float, threshold: float = 0.5) -> bool:
    """True if OOS Sharpe is < *threshold* of IS Sharpe.

    Returns False when IS Sharpe is non-positive (overfit detection only
    makes sense for strategies that look good in-sample).
    """
    if is_sharpe <= 0:
        return False
    return oos_sharpe < threshold * is_sharpe
