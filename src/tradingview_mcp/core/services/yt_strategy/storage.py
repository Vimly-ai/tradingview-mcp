"""Persisted-run storage under STRATEGY_STORAGE_DIR/strategies/<slug>/."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _validate_slug(slug: str) -> str:
    """Ensure *slug* is a safe filesystem name with no path separators.

    Raises ValueError on traversal patterns or empty input.
    """
    if not slug or slug in (".", ".."):
        raise ValueError(f"Invalid slug {slug!r}: must be a non-empty identifier.")
    if "/" in slug or "\\" in slug or ".." in slug:
        raise ValueError(f"Invalid slug {slug!r}: must not contain path separators or '..'.")
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Invalid slug {slug!r}: must start with alphanumeric and contain only [A-Za-z0-9._-]."
        )
    return slug


@dataclass
class RunArtifacts:
    strategy_py: str
    strategy_pine: str
    report_json: dict[str, Any]
    transcript: str
    equity_curve_png: bytes


def _storage_dir() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    d = Path(base) / "strategies"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(slug: str, artifacts: RunArtifacts) -> Path:
    """Persist *artifacts* under storage/<slug>/. Returns the dir path."""
    _validate_slug(slug)
    d = _storage_dir() / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "strategy.py").write_text(artifacts.strategy_py)
    (d / "strategy.pine").write_text(artifacts.strategy_pine)
    (d / "report.json").write_text(json.dumps(artifacts.report_json, indent=2, default=str))
    (d / "transcript.txt").write_text(artifacts.transcript)
    if artifacts.equity_curve_png:
        (d / "equity_curve.png").write_bytes(artifacts.equity_curve_png)
    return d


def load_run(slug: str) -> RunArtifacts:
    _validate_slug(slug)
    d = _storage_dir() / slug
    if not d.exists():
        raise FileNotFoundError(f"No run at slug {slug!r}")
    png_path = d / "equity_curve.png"
    return RunArtifacts(
        strategy_py=(d / "strategy.py").read_text() if (d / "strategy.py").exists() else "",
        strategy_pine=(d / "strategy.pine").read_text() if (d / "strategy.pine").exists() else "",
        report_json=json.loads((d / "report.json").read_text()) if (d / "report.json").exists() else {},
        transcript=(d / "transcript.txt").read_text() if (d / "transcript.txt").exists() else "",
        equity_curve_png=png_path.read_bytes() if png_path.exists() else b"",
    )


def list_runs() -> list[dict[str, Any]]:
    """Return summaries of all persisted runs."""
    d = _storage_dir()
    summaries: list[dict[str, Any]] = []
    for sub in sorted(d.iterdir()):
        if not sub.is_dir():
            continue
        report_path = sub / "report.json"
        report: dict[str, Any] = {}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text())
            except json.JSONDecodeError:
                report = {}
        summaries.append({
            "slug": sub.name,
            "path": str(sub),
            "sharpe": report.get("out_of_sample", {}).get("sharpe", report.get("sharpe")),
            "n_trades": report.get("out_of_sample", {}).get("n_trades", report.get("n_trades")),
            "mtime": sub.stat().st_mtime,
        })
    return summaries
