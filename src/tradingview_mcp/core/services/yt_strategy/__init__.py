"""YouTube → strategy → backtest pipeline.

Submodules:
- transcript: YouTube URL → plaintext transcript
- rule_extractor: transcript → StrategySpec stub
- codegen: Python + Pine v6 templates
- data: unified OHLCV fetch (Yahoo + Binance) + cost profiles
- runner: sandboxed strategy exec + backtest
- walkforward: out-of-sample validation
- autotune: deterministic parameter optimization
- storage: persisted runs
"""
from __future__ import annotations
