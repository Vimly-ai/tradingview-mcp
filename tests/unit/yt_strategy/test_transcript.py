"""Tests for transcript.py."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tradingview_mcp.core.services.yt_strategy.transcript import (
    TranscriptResult,
    TranscriptUnavailable,
    fetch_transcript,
    extract_video_id,
    _parse_vtt,
)


class TestExtractVideoId:
    def test_standard_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_with_extra_params(self):
        assert extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Not a valid YouTube URL"):
            extract_video_id("https://vimeo.com/12345")

    def test_shorts_url(self):
        assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url_with_si_param(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ?si=abc123def") == "dQw4w9WgXcQ"


class TestFetchTranscript:
    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_uses_api_when_available(self, mock_api, tmp_path, monkeypatch):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        mock_api.get_transcript.return_value = [
            {"text": "Hello", "start": 0.0, "duration": 1.0},
            {"text": "world", "start": 1.0, "duration": 1.0},
        ]
        result = fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert isinstance(result, TranscriptResult)
        assert "Hello world" in result.text
        assert result.source == "youtube-transcript-api"

    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_caches_result(self, mock_api, tmp_path, monkeypatch):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        mock_api.get_transcript.return_value = [{"text": "Hi", "start": 0.0, "duration": 1.0}]
        # First call hits the API
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert mock_api.get_transcript.call_count == 1
        # Second call hits the cache
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert mock_api.get_transcript.call_count == 1

    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_cache_expires_after_ttl(self, mock_api, tmp_path, monkeypatch):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        monkeypatch.setenv("YT_TRANSCRIPT_CACHE_TTL_H", "0")  # immediate expiry
        mock_api.get_transcript.return_value = [{"text": "Hi", "start": 0.0, "duration": 1.0}]
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert mock_api.get_transcript.call_count == 2  # cache was bypassed

    @patch("tradingview_mcp.core.services.yt_strategy.transcript._fetch_via_ytdlp")
    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_falls_back_to_ytdlp_when_api_fails(
        self, mock_api, mock_ytdlp, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        mock_api.get_transcript.side_effect = Exception("API blocked")
        mock_ytdlp.return_value = TranscriptResult(
            text="from ytdlp",
            language="en",
            duration_s=120,
            title="Test",
            channel="TestCh",
            source="yt-dlp",
            video_id="dQw4w9WgXcQ",
        )
        result = fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert result.text == "from ytdlp"
        assert result.source == "yt-dlp"

    @patch("tradingview_mcp.core.services.yt_strategy.transcript._fetch_via_ytdlp")
    @patch("tradingview_mcp.core.services.yt_strategy.transcript.YouTubeTranscriptApi")
    def test_raises_when_both_sources_fail(
        self, mock_api, mock_ytdlp, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("STRATEGY_STORAGE_DIR", str(tmp_path))
        mock_api.get_transcript.side_effect = Exception("API blocked")
        mock_ytdlp.side_effect = Exception("ytdlp blocked too")
        with pytest.raises(TranscriptUnavailable):
            fetch_transcript("https://youtu.be/dQw4w9WgXcQ")


class TestParseVtt:
    def test_dedupes_consecutive_repeats(self):
        vtt = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.000\nhello world\n\n"
            "00:00:01.000 --> 00:00:03.000\nhello world\n\n"
            "00:00:02.000 --> 00:00:04.000\nthis is new\n\n"
        )
        result = _parse_vtt(vtt)
        assert result.count("hello world") == 1
        assert "this is new" in result

    def test_strips_inline_tags(self):
        vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n<c.color>hello</c> world\n"
        assert _parse_vtt(vtt) == "hello world"

    def test_empty_vtt(self):
        assert _parse_vtt("WEBVTT\n\n") == ""
