"""YouTube URL → plaintext transcript with caching and fallback."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "youtube-transcript-api is not installed. Run: uv sync"
    ) from e


@dataclass
class TranscriptResult:
    """Plaintext transcript + video metadata."""

    text: str
    language: str
    duration_s: int
    title: str
    channel: str
    source: str  # "youtube-transcript-api" | "yt-dlp" | "cache"
    video_id: str


class TranscriptUnavailable(Exception):
    """Raised when neither youtube-transcript-api nor yt-dlp can fetch a transcript."""


_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^&]*&)*v=|embed/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str) -> str:
    """Parse a YouTube URL and return its 11-character video ID.

    Raises:
        ValueError: if *url* is not a recognizable YouTube URL.
    """
    m = _VIDEO_ID_RE.search(url)
    if not m:
        raise ValueError(f"Not a valid YouTube URL: {url!r}")
    return m.group(1)


def _cache_dir() -> Path:
    base = os.environ.get(
        "STRATEGY_STORAGE_DIR", os.path.expanduser("~/.tradingview_mcp_data")
    )
    d = Path(base) / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_ttl_s() -> float:
    try:
        return float(os.environ.get("YT_TRANSCRIPT_CACHE_TTL_H", "24")) * 3600
    except ValueError:
        return 24 * 3600


def _cache_get(video_id: str) -> TranscriptResult | None:
    path = _cache_dir() / f"{video_id}.json"
    if not path.exists():
        return None
    ttl = _cache_ttl_s()
    if ttl <= 0:
        return None
    if time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    data["source"] = "cache"
    return TranscriptResult(**data)


def _cache_set(result: TranscriptResult) -> None:
    path = _cache_dir() / f"{result.video_id}.json"
    try:
        path.write_text(json.dumps(asdict(result)))
    except OSError:  # disk full, permission denied — silent best-effort
        pass


def _fetch_via_api(video_id: str) -> TranscriptResult:
    """Primary path: youtube-transcript-api."""
    chunks = YouTubeTranscriptApi.get_transcript(video_id)
    text = " ".join(c["text"].strip() for c in chunks if c.get("text"))
    duration = int(sum(c.get("duration", 0) for c in chunks))
    return TranscriptResult(
        text=text,
        language="en",  # the lib doesn't expose this on the basic call
        duration_s=duration,
        title="",  # unavailable from this lib
        channel="",
        source="youtube-transcript-api",
        video_id=video_id,
    )


def _fetch_via_ytdlp(video_id: str) -> TranscriptResult:
    """Fallback path: yt-dlp with auto-subs.

    Uses yt-dlp's Python API rather than CLI for cleaner error handling.
    """
    try:
        import yt_dlp  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise TranscriptUnavailable("yt-dlp not installed") from e

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=False
        )

    subs = (info or {}).get("automatic_captions", {})
    track = None
    for lang in ("en", "en-US", "en-GB"):
        if lang in subs and subs[lang]:
            track = subs[lang][0]
            break
    if not track or not track.get("url"):
        raise TranscriptUnavailable(f"No English auto-captions for video {video_id}")

    import requests  # type: ignore

    resp = requests.get(track["url"], timeout=20)
    resp.raise_for_status()
    vtt = resp.text
    # Strip VTT headers and timing lines; keep only spoken text.
    text_lines = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
            continue
        # remove inline tags like <c.colorname>
        line = re.sub(r"<[^>]+>", "", line)
        text_lines.append(line)
    text = " ".join(text_lines)

    return TranscriptResult(
        text=text,
        language=track.get("language", "en"),
        duration_s=int(info.get("duration", 0) if info else 0),
        title=str(info.get("title", "") if info else ""),
        channel=str(info.get("uploader", "") if info else ""),
        source="yt-dlp",
        video_id=video_id,
    )


def fetch_transcript(url: str) -> TranscriptResult:
    """Fetch a transcript for *url*.

    Tries cache, then ``youtube-transcript-api``, then ``yt-dlp``.

    Raises:
        ValueError: if *url* is not a valid YouTube URL.
        TranscriptUnavailable: if no source could supply a transcript.
    """
    video_id = extract_video_id(url)

    cached = _cache_get(video_id)
    if cached is not None:
        return cached

    api_err: Exception | None = None
    try:
        result = _fetch_via_api(video_id)
    except Exception as e:
        api_err = e
    else:
        _cache_set(result)
        return result

    try:
        result = _fetch_via_ytdlp(video_id)
    except Exception as ytdlp_err:
        raise TranscriptUnavailable(
            f"Both fetchers failed for {video_id}; "
            f"api_err={api_err!r}; ytdlp_err={ytdlp_err!r}"
        ) from ytdlp_err

    _cache_set(result)
    return result
