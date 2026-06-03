"""StrategySpec dataclass + MVP rule-extraction stub.

Real rule extraction is delegated to the assistant in Claude Desktop, which
reads the transcript and fills in skeletons returned by codegen.py. This
module exists for shape stability — every Tool 1 call returns a
StrategySpec the assistant can build on.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StrategySpec:
    name: str = ""
    entry_rules: list[str] = field(default_factory=list)
    exit_rules: list[str] = field(default_factory=list)
    indicators_used: list[str] = field(default_factory=list)
    timeframe_hint: str | None = None
    asset_hint: str | None = None
    position_sizing: str | None = None
    risk_management: str | None = None
    confidence: float = 0.0
    raw_transcript: str = ""


def extract_rules(transcript: str) -> StrategySpec:
    """MVP stub: wrap the transcript as a single entry rule with low confidence."""
    if not transcript.strip():
        return StrategySpec()
    return StrategySpec(
        entry_rules=[transcript],
        raw_transcript=transcript,
        confidence=0.1,
    )
