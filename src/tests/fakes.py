"""Stand-ins shared by more than one test module."""

import threading
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


def mock_ydl(return_code=0) -> MagicMock:
    """A YoutubeDL that works as a context manager and whose ``download`` returns ``return_code``."""
    ydl = MagicMock()
    ydl.download.return_value = return_code
    ydl.__enter__ = MagicMock(return_value=ydl)
    ydl.__exit__ = MagicMock(return_value=False)
    return ydl


class YdlBuilder:
    """Stands in for the YoutubeDL class: hands out one instance and keeps the options it was built with."""

    def __init__(self, ydl):
        self.ydl, self.opts = ydl, {}

    def __call__(self, opts):
        self.opts.update(opts)
        return self.ydl


@contextmanager
def downloading_with(ydl):
    """Run ``src.downloads`` against ``ydl``; yields the builder that records the options."""
    builder = YdlBuilder(ydl)
    with patch("src.downloads.yt_dlp.YoutubeDL", side_effect=builder), \
            patch("src.downloads.base_opts", return_value={}):
        yield builder


def download_config(tmp_path) -> MagicMock:
    """A config with the attributes the download functions read."""
    cfg = MagicMock()
    cfg.video_dir = tmp_path / "videos"
    cfg.audio_dir = tmp_path / "audio"
    cfg.video_format = "%(title)s.%(ext)s"
    cfg.audio_format = "%(title)s.%(ext)s"
    cfg.preferred_quality = "1080"
    cfg.cookies_file = None
    return cfg


def run_in_threads(target, count: int) -> None:
    """Call ``target(n)`` for each n below ``count``, each on its own thread, and wait for all of them."""
    threads = [threading.Thread(target=target, args=(n,)) for n in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def silence_detail_workers(monkeypatch) -> None:
    """Stop the detail panel from starting its focus and thumbnail workers."""
    for name in ("_kick_focus", "_kick_thumb"):
        monkeypatch.setattr(f"src.tui.screens.mixins.detail_focus.DetailFocusMixin.{name}", lambda *a: None)


def silence_empty_feed_modal(monkeypatch) -> None:
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a, **k: None)
