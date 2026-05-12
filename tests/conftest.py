"""Shared pytest fixtures for TermTube test suite."""

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Static fixture data ──────────────────────────────────────────────────────

SAMPLE_ENTRIES = [
    {
        "id": "abc123def45",
        "title": "How to Build a TUI App",
        "uploader": "CodeChannel",
        "channel": "CodeChannel",
        "channel_id": "UCxxxxxxxx1",
        "duration": 612,
        "view_count": 150000,
        "upload_date": "20250101",
        "thumbnail": "https://i.ytimg.com/vi/abc123def45/maxresdefault.jpg",
        "webpage_url": "https://www.youtube.com/watch?v=abc123def45",
        "description": "In this video we build a terminal user interface.",
    },
    {
        "id": "xyz789ghj12",
        "title": "Best Albums of 2025",
        "uploader": "MusicReviewer",
        "channel": "MusicReviewer",
        "channel_id": "UCxxxxxxxx2",
        "duration": 1845,
        "view_count": 89000,
        "upload_date": "20250315",
        "thumbnail": "https://i.ytimg.com/vi/xyz789ghj12/maxresdefault.jpg",
        "webpage_url": "https://www.youtube.com/watch?v=xyz789ghj12",
        "description": "My top picks for music this year.",
    },
    {
        "id": "qwe456rty78",
        "title": "10 Minute Abs Workout",
        "uploader": "FitnessGuru",
        "channel": "FitnessGuru",
        "channel_id": "UCxxxxxxxx3",
        "duration": 605,
        "view_count": 2300000,
        "upload_date": "20250420",
        "thumbnail": "https://i.ytimg.com/vi/qwe456rty78/maxresdefault.jpg",
        "webpage_url": "https://www.youtube.com/watch?v=qwe456rty78",
        "description": None,
    },
]

SAMPLE_FORMATS = [
    {"format_id": "251", "acodec": "opus", "vcodec": "none", "abr": 160,
     "url": "https://rr1.googlevideo.com/audio?expire=9999999999&itag=251"},
    {"format_id": "140", "acodec": "mp4a.40.2", "vcodec": "none", "abr": 128,
     "url": "https://rr1.googlevideo.com/audio?expire=9999999999&itag=140"},
    {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "height": 1080, "tbr": 4000,
     "url": "https://rr1.googlevideo.com/video?expire=9999999999&itag=137"},
    {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none", "height": 720, "tbr": 2500,
     "url": "https://rr1.googlevideo.com/video?expire=9999999999&itag=136"},
    {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "height": 360, "tbr": 700,
     "url": "https://rr1.googlevideo.com/combined?expire=9999999999&itag=18"},
]


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_entries():
    """List of realistic video entry dicts."""
    return [dict(e) for e in SAMPLE_ENTRIES]


@pytest.fixture
def sample_formats():
    """List of realistic yt-dlp format dicts."""
    return [dict(f) for f in SAMPLE_FORMATS]


@pytest.fixture
def temp_cache(tmp_path, monkeypatch):
    """Set up temporary cache directories and return a Cache instance."""
    video_dir = tmp_path / "videos"
    thumb_dir = tmp_path / "thumbs"
    playlist_video_dir = tmp_path / "playlist_videos"
    playlist_thumb_dir = tmp_path / "playlist_thumbs"

    video_dir.mkdir()
    thumb_dir.mkdir()
    playlist_video_dir.mkdir()
    playlist_thumb_dir.mkdir()

    monkeypatch.setattr("src.cache.VIDEO_DIR", video_dir)
    monkeypatch.setattr("src.cache.THUMB_DIR", thumb_dir)
    monkeypatch.setattr("src.cache.PLAYLIST_VIDEO_DIR", playlist_video_dir)
    monkeypatch.setattr("src.cache.PLAYLIST_THUMB_DIR", playlist_thumb_dir)
    monkeypatch.setattr("src.cache.CACHE_DIR", tmp_path)
    monkeypatch.setattr("src.cache._SUPPRESSED_PATH", tmp_path / "suppressed.json")

    from src.cache import Cache
    cache = Cache({"home": 3600, "metadata": 86400, "search": 1800, "subscriptions": 3600})
    return cache


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Create a minimal config in a temp directory."""
    config_path = tmp_path / "config.yaml"
    from src.config import Config
    config = Config(path=str(config_path))
    return config


@pytest.fixture
def temp_playlists(tmp_path, monkeypatch):
    """Redirect playlist storage to temp directory."""
    pl_path = tmp_path / "playlists.json"
    monkeypatch.setattr("src.playlist._PLAYLISTS_PATH", pl_path)
    return pl_path


@pytest.fixture
def temp_history(tmp_path, monkeypatch):
    """Redirect history storage to temp directory."""
    hist_path = tmp_path / "history.json"
    monkeypatch.setattr("src.history.HISTORY_PATH", hist_path)
    return hist_path


@pytest.fixture
def mock_ytdlp_feeds(sample_entries):
    """Patch _stream_json_lines to yield sample entries."""
    with patch("src.ytdlp._stream_json_lines", return_value=iter(sample_entries)):
        yield sample_entries


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.Popen with a configurable mock."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.returncode = 0
    mock_proc.stdout = iter([])
    mock_proc.stderr = MagicMock()
    mock_proc.communicate.return_value = ("", "")
    mock_proc.wait.return_value = 0
    mock_proc.pid = 12345

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        yield mock_popen, mock_proc


@pytest.fixture
def mock_mpv_ipc():
    """Patch mpv IPC functions."""
    with patch("src.player.send_ipc_command") as mock_send, \
         patch("src.player.poll_audio_properties", return_value=(10.0, 300.0, False)) as mock_poll:
        yield mock_send, mock_poll
