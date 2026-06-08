"""Capture screenshot + DOM dump + (opt-in) trace on tool failure."""
from __future__ import annotations

import os
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator


def _storage_root() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    return Path(base)


def _max_count() -> int:
    try:
        return max(1, int(os.environ.get("TV_BROWSER_DEBUG_MAX", "20")))
    except ValueError:
        return 20


@asynccontextmanager
async def debug_on_failure(page: Any, tool_name: str) -> AsyncIterator[None]:
    """Wrap a tool body. On exception, dump screenshot + DOM + error text to
    ~/.tradingview_mcp_data/browser_debug/<timestamp>-<tool>/.

    Re-raises the original exception with .debug_artifacts_path attached.
    Successful operations write NO artifacts here.
    """
    try:
        yield
    except Exception as e:
        ts = time.strftime("%Y-%m-%dT%H-%M-%S")
        folder = _storage_root() / "browser_debug" / f"{ts}-{tool_name}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            try:
                png = await page.screenshot()
                (folder / "screenshot.png").write_bytes(png)
            except Exception:
                pass
            try:
                html = await page.content()
                (folder / "dom.html").write_text(html)
            except Exception:
                pass
            try:
                (folder / "error.txt").write_text(
                    f"{type(e).__name__}: {e}\n\n" + traceback.format_exc()
                )
            except Exception:
                pass
            rotate_artifacts(folder.parent, _max_count())
        except Exception:
            pass

        try:
            setattr(e, "debug_artifacts_path", str(folder))
        except Exception:
            pass
        raise


def rotate_artifacts(root: Path, max_count: int = 20) -> None:
    """Keep newest *max_count* subdirs under *root*; delete the rest."""
    if not root.exists():
        return
    subdirs = [d for d in root.iterdir() if d.is_dir()]
    subdirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    for d in subdirs[max_count:]:
        try:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
