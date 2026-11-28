"""Fixtures for headless TUI tests."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src import history, playlist
from src.tests.fakes import silence_detail_workers, silence_empty_feed_modal
from src.tests.tui.layout_data import LONG, long_channels, long_entries
from src.tui.audio_controller import AudioController
from src.tui.screens.download_modal import DownloadModal
from src.tui.screens.watch_modal import WatchModal


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
    monkeypatch.setattr("src.search_history.SEARCH_HISTORY_PATH", tmp_path / "search_history.json")
    monkeypatch.setattr("src.innertube.fetch_suggestions", lambda query, **_: [])
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


@pytest.fixture
def quiet_app(app, temp_playlists, monkeypatch):
    """The app with Home's startup load and every modal's and detail panel's worker silenced."""
    silence_detail_workers(monkeypatch)
    silence_empty_feed_modal(monkeypatch)
    monkeypatch.setattr(DownloadModal, "_start_download", lambda self: None)
    monkeypatch.setattr(WatchModal, "_launch_video", lambda self: None)
    monkeypatch.setattr(WatchModal, "_poll_mpv", lambda self: None)
    monkeypatch.setattr(AudioController, "_launch_worker", lambda *a, **k: None)
    return app


@pytest.fixture
def fake_data(monkeypatch, tmp_path, temp_history, temp_channels, temp_playlists):
    """Fake feeds, history, library files and playlists; nothing leaves the process."""
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: long_entries())
    monkeypatch.setattr("src.ytdlp.fetch_subscribed_channels", lambda *a, **k: long_channels())
    monkeypatch.setattr("src.ytdlp.fetch_search_batch", lambda query, *a, count=50, **k: long_entries(count))
    monkeypatch.setattr("src.tui.screens.mixins.feed_loader.resolve_browser", lambda config: "firefox")
    silence_detail_workers(monkeypatch)
    silence_empty_feed_modal(monkeypatch)
    for entry in long_entries(12):
        history.add(entry)
    videos, audio = tmp_path / "vid", tmp_path / "aud"
    for directory, ext, kind in ((videos, "mp4", "v"), (audio, "mp3", "a")):
        _add_downloads(directory, ext, kind)
    return videos, audio


def _add_downloads(directory, ext, kind):
    directory.mkdir()
    for i in range(8):
        vid = f"{kind}{i:010d}"
        (directory / f"{vid}.{ext}").write_bytes(b"x" * 5)
        sidecar = {"id": vid, "title": f"{LONG} {vid}", "uploader": "Alpha", "duration": 100,
                   "upload_date": "20260101"}
        (directory / f"{vid}.info.json").write_text(json.dumps(sidecar), encoding="utf-8")


@pytest.fixture
def main_app(app, fake_data):
    videos, audio = fake_data
    app.config._data["video_dir"], app.config._data["audio_dir"] = str(videos), str(audio)
    for i in range(3):
        playlist.create(f"Playlist number {i}", long_entries(4))
    return app
