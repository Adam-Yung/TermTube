"""TUI interaction tests for MainScreen navigation."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
def mock_all_externals(tmp_path, monkeypatch):
    """Mock all external dependencies so TermTubeApp can boot."""
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
        {"id": f"vid{i:03d}", "title": f"Test Video {i}", "uploader": f"Channel {i}",
         "duration": 100 + i * 60, "view_count": 1000 * i, "upload_date": f"2025010{i}",
         "webpage_url": f"https://www.youtube.com/watch?v=vid{i:03d}"}
        for i in range(1, 11)
    ]

    with patch("src.ytdlp._stream_json_lines", return_value=iter(entries)), \
               \
         patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = ("", "")
        mock_popen.return_value = mock_proc
        yield {"entries": entries, "popen": mock_popen, "proc": mock_proc}


@pytest.fixture
def app(mock_all_externals, tmp_path):
    """Create a TermTubeApp instance with mocked externals."""
    from src.config import Config
    from src.tui.app import TermTubeApp
    config = Config(path=str(tmp_path / "config.yaml"))
    config._data["thumbnail_warning_dismissed"] = True
    config._data["cookie_warning_dismissed"] = True
    config._data["cookies_file"] = ""
    return TermTubeApp(config)


async def test_app_boots_without_crash(app):
    """The app should start and compose without errors."""
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        assert app.screen is not None


async def test_quit_key_exits(app):
    """Pressing q should quit the app."""
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("q")
        await pilot.pause(0.1)


async def test_help_toggle(app):
    """Pressing ? should show help content."""
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("question_mark")
        await pilot.pause(0.2)


async def test_search_modal_opens(app):
    """Pressing / should open the search modal."""
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.5)
        await pilot.press("slash")
        await pilot.pause(1.0)
        screen_names = [type(s).__name__ for s in app.screen_stack]
        assert "SearchModal" in screen_names, f"SearchModal not in screen_stack: {screen_names}"
