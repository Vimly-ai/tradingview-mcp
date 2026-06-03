from __future__ import annotations

import pandas as pd
import pytest

from tradingview_mcp.core.services.yt_strategy.walkforward import (
    walk_forward_split,
    detect_overfit,
)


def _fixture_df():
    from pathlib import Path
    csv = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_ohlcv.csv"
    return pd.read_csv(csv, parse_dates=["Date"], index_col="Date")


def test_split_yields_5_folds_from_500_bars():
    df = _fixture_df()
    folds = walk_forward_split(df, n_chunks=6)
    assert len(folds) == 5

def test_each_fold_test_immediately_follows_train():
    df = _fixture_df()
    folds = walk_forward_split(df, n_chunks=6)
    for train, test in folds:
        assert train.index[-1] < test.index[0], "Test must start after train ends"

def test_train_is_expanding():
    df = _fixture_df()
    folds = walk_forward_split(df, n_chunks=6)
    lengths = [len(train) for train, _ in folds]
    assert lengths == sorted(lengths), "Train should expand each fold"

def test_fold_test_disjoint_from_train():
    df = _fixture_df()
    folds = walk_forward_split(df, n_chunks=6)
    for train, test in folds:
        assert set(train.index).isdisjoint(set(test.index))

def test_detect_overfit_fires_when_oos_half_is():
    assert detect_overfit(is_sharpe=2.0, oos_sharpe=0.5) is True
    assert detect_overfit(is_sharpe=2.0, oos_sharpe=1.5) is False

def test_detect_overfit_handles_negative_is():
    assert detect_overfit(is_sharpe=-0.5, oos_sharpe=0.5) is False
