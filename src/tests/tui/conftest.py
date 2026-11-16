"""Fixtures for headless TUI tests."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_all_externals(tmp_path, monkeypatch):
    """Mock all external dependencies so TermTubeApp can boot."""
    monkeypatch.setattr("src.tui.screens.main_screen._force_exit", lambda: None)
    monkeypatch.setattr("src.cache.CACHE_DIR", tmp_path)
    monkeypatch.setattr("src.cache.VIDEO_DIR", tmp_path / "videos")
    monkeypatch.setattr("src.cache.THUMB_DIR", tmp_path / "thumbs")
    monkeypatch.setattr("src.cache.PLAYLIST_VIDEO_DIR", tmp_path / "playlist_videos")
    monkeypatch.setattr("src.cache.PLAYLIST_THUMB_DIR", tmp_path / "playlist_thumbs")
    monkeypatch.setattr("src.cache._SUPPRESSED_PATH", tmp_path / "suppressed.json")
    (tmp_path / "videos").mkdir(exist_ok=True)
    (tmp_path / "thumbs").mkdir(exist_ok=True)
    (tmp_path / "playlist_videos").mkdir(exist_ok=True)
    (tmp_path / "playlist_thumbs").mkdir(exist_ok=True)

    entries = [
        {"id": f"vid{i:08d}", "title": f"Test Video {i}", "uploader": f"Channel {i}",
         "duration": 100 + i * 60, "view_count": 1000 * i, "upload_date": f"2025010{i}",
         "webpage_url": f"https://www.youtube.com/watch?v=vid{i:08d}"}
        for i in range(1, 11)
    ]

    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = {"entries": iter(entries)}

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        yield {"entries": entries, "ydl": mock_ydl}


@pytest.fixture
def app(mock_all_externals, tmp_path):
    """Create a TermTubeApp instance with mocked externals."""
    from src.config import Config
    from src.tui.app import TermTubeApp
    config = Config(path=str(tmp_path / "config.yaml"))
    config._data["thumbnail_warning_dismissed"] = True
    config._data["browser"] = "none"
    return TermTubeApp(config)
