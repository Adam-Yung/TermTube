"""DownloadModal: Esc must stop the running download, not only close the dialog."""

import threading
from unittest.mock import patch

from src.tui.screens.download_modal import DownloadModal


async def test_escape_sets_the_cancel_handle_and_dismisses(app):
    seen = {}
    started = threading.Event()

    def fake_download(video_id, config, *, cancel, **kwargs):
        seen["cancel"] = cancel
        started.set()
        cancel.wait(5)
        return False

    results = []
    async with app.run_test(size=(100, 30)) as pilot:
        with patch("src.downloads.download_video_with_progress", fake_download):
            app.push_screen(DownloadModal("AAAAAAAAAAA", {"title": "t"}), results.append)
            await pilot.pause(0.2)
            assert started.wait(2)
            assert not seen["cancel"].is_set()
            await pilot.press("escape")
            await pilot.pause(0.2)
    assert seen["cancel"].is_set() and results == [False]
