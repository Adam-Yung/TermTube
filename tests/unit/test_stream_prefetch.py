"""Tests for stream URL prefetch logic in ytdlp.fetch_stream_urls."""

import sys
import time
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from src.ytdlp import (
    fetch_stream_urls,
    _pick_best_audio_url,
    _pick_best_video_url,
    _extract_expire,
)


class TestPickBestAudioUrl:
    def test_picks_highest_bitrate(self):
        formats = [
            {"acodec": "opus", "vcodec": "none", "abr": 128, "url": "http://a/128"},
            {"acodec": "opus", "vcodec": "none", "abr": 256, "url": "http://a/256"},
            {"acodec": "opus", "vcodec": "none", "abr": 64, "url": "http://a/64"},
        ]
        assert _pick_best_audio_url(formats) == "http://a/256"

    def test_ignores_video_formats(self):
        formats = [
            {"acodec": "opus", "vcodec": "vp9", "abr": 256, "url": "http://av/256"},
            {"acodec": "opus", "vcodec": "none", "abr": 128, "url": "http://a/128"},
        ]
        assert _pick_best_audio_url(formats) == "http://a/128"

    def test_returns_none_when_no_audio(self):
        formats = [
            {"acodec": "none", "vcodec": "vp9", "height": 1080, "url": "http://v/1080"},
        ]
        assert _pick_best_audio_url(formats) is None

    def test_ignores_entries_without_url(self):
        formats = [
            {"acodec": "opus", "vcodec": "none", "abr": 256},
            {"acodec": "opus", "vcodec": "none", "abr": 128, "url": "http://a/128"},
        ]
        assert _pick_best_audio_url(formats) == "http://a/128"


class TestPickBestVideoUrl:
    def test_picks_highest_resolution(self):
        formats = [
            {"vcodec": "vp9", "acodec": "none", "height": 720, "url": "http://v/720"},
            {"vcodec": "vp9", "acodec": "none", "height": 1080, "url": "http://v/1080"},
            {"vcodec": "vp9", "acodec": "none", "height": 480, "url": "http://v/480"},
        ]
        assert _pick_best_video_url(formats) == "http://v/1080"

    def test_ignores_audio_only_formats(self):
        formats = [
            {"vcodec": "none", "acodec": "opus", "abr": 256, "url": "http://a/256"},
            {"vcodec": "vp9", "acodec": "none", "height": 720, "url": "http://v/720"},
        ]
        assert _pick_best_video_url(formats) == "http://v/720"

    def test_returns_none_when_no_video(self):
        formats = [
            {"vcodec": "none", "acodec": "opus", "abr": 256, "url": "http://a/256"},
        ]
        assert _pick_best_video_url(formats) is None


class TestExtractExpire:
    def test_extracts_expire_from_youtube_url(self):
        url = "https://rr2.googlevideo.com/videoplayback?expire=1700000000&ei=abc&ip=1.2.3.4"
        assert _extract_expire(url) == 1700000000

    def test_returns_zero_on_no_expire(self):
        url = "https://example.com/stream?foo=bar"
        assert _extract_expire(url) == 0

    def test_returns_zero_on_empty(self):
        assert _extract_expire("") == 0

    def test_returns_zero_on_invalid_expire(self):
        url = "https://example.com?expire=notanumber"
        assert _extract_expire(url) == 0


class TestFetchStreamUrls:
    def test_returns_urls_on_success(self):
        fake_info = {
            "id": "abc123",
            "formats": [
                {"acodec": "opus", "vcodec": "none", "abr": 256,
                 "url": "https://rr.googlevideo.com/audio?expire=9999999999"},
                {"vcodec": "vp9", "acodec": "none", "height": 1080,
                 "url": "https://rr.googlevideo.com/video?expire=9999999999"},
            ],
        }

        with patch("src.ytdlp._stream_json_lines", return_value=iter([fake_info])):
            config = MagicMock()
            config.cookie_args.return_value = []
            result = fetch_stream_urls("abc123", config)

        assert result is not None
        assert result["audio_url"] == "https://rr.googlevideo.com/audio?expire=9999999999"
        assert result["video_url"] == "https://rr.googlevideo.com/video?expire=9999999999"
        assert result["expire"] == 9999999999
        assert result["fetched_at"] > 0

    def test_returns_none_when_no_formats(self):
        fake_info = {"id": "abc123", "formats": []}

        with patch("src.ytdlp._stream_json_lines", return_value=iter([fake_info])):
            config = MagicMock()
            config.cookie_args.return_value = []
            result = fetch_stream_urls("abc123", config)

        assert result is None

    def test_returns_none_on_empty_response(self):
        with patch("src.ytdlp._stream_json_lines", return_value=iter([])):
            config = MagicMock()
            config.cookie_args.return_value = []
            result = fetch_stream_urls("abc123", config)

        assert result is None

    def test_partial_result_audio_only(self):
        fake_info = {
            "id": "abc123",
            "formats": [
                {"acodec": "opus", "vcodec": "none", "abr": 256,
                 "url": "https://rr.googlevideo.com/audio?expire=9999999999"},
            ],
        }

        with patch("src.ytdlp._stream_json_lines", return_value=iter([fake_info])):
            config = MagicMock()
            config.cookie_args.return_value = []
            result = fetch_stream_urls("abc123", config)

        assert result is not None
        assert result["audio_url"] is not None
        assert result["video_url"] is None
