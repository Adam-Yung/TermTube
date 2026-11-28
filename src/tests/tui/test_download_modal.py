"""DownloadModal: Esc must stop the running download, not only close the dialog."""

import threading
from functools import partial
from unittest.mock import MagicMock, patch

from src.tui.screens.download_modal import DownloadModal


def _wait_for_cancel(seen, started, video_id, config, *, cancel, **kwargs):
    seen["cancel"] = cancel
    started.set()
    cancel.wait(5)
    return False


async def test_escape_sets_the_cancel_handle_and_dismisses(app):
    seen = {}
    started = threading.Event()

    results = []
    async with app.run_test(size=(100, 30)) as pilot:
        with patch("src.downloads.download_video_with_progress", partial(_wait_for_cancel, seen, started)):
            app.push_screen(DownloadModal("AAAAAAAAAAA", {"title": "t"}), results.append)
            await pilot.pause(0.2)
            assert started.wait(2)
            assert not seen["cancel"].is_set()
            await pilot.press("escape")
            await pilot.pause(0.2)
    assert seen["cancel"].is_set() and results == [False]


async def test_finished_download_refreshes_one_item_and_pins_it_offline(app, tmp_path):
    import json

    from PIL import Image

    from src.tui.screens.download_modal import DownloadModal

    videos = tmp_path / "vid"
    videos.mkdir()
    (videos / "clip.mp4").write_bytes(b"x")
    sidecar = {"id": "vid1", "title": "Clip", "formats": [{}]}
    (videos / "clip.info.json").write_text(json.dumps(sidecar), encoding="utf-8")
    Image.new("RGB", (4, 4), "red").save(videos / "clip.webp", "WEBP")
    pinned = {}
    app.cache = type("C", (), {"pin_video": lambda s, i, e: pinned.update(entry=e),
                               "pin_thumb": lambda s, i, source=None: pinned.update(thumb=source)})()
    async with app.run_test(size=(100, 30)) as pilot:
        modal = DownloadModal("vid1", {"id": "vid1", "title": "Clip"})
        modal._files = [str(videos / "clip.f137.mp4"), str(videos / "clip.mp4")]
        modal.dismiss = lambda *_: None
        modal._on_done(True)
        await pilot.pause(0.1)
    assert pinned["entry"] == {"id": "vid1", "title": "Clip", "uploader": None, "channel": None, "channel_id": None,
                               "duration": None, "upload_date": None, "view_count": None, "webpage_url": None,
                               "tags": None, "thumbnail": None, "description": ""}
    assert pinned["thumb"] == videos / "clip.jpg" and (videos / "clip.jpg").exists()


async def test_a_download_that_cannot_register_tells_the_user_and_still_closes(app, tmp_path, monkeypatch):
    from src.tui.screens.download_modal import DownloadModal

    monkeypatch.setattr("src.library.finish_download", MagicMock(side_effect=OSError("disk full")))
    told, closed = [], []
    monkeypatch.setattr(type(app), "notify", lambda self, msg, **kw: told.append(msg))
    async with app.run_test(size=(100, 30)) as pilot:
        modal = DownloadModal("vid1", {"id": "vid1", "title": "Clip"})
        modal._files = [str(tmp_path / "a [b].mp4")]
        modal.dismiss = lambda *a: closed.append(a)
        modal._on_done(True)
        await pilot.pause(0.1)
    assert closed == [(True,)] and len(told) == 1 and "a [b].mp4" in told[0] and "next scan" in told[0]
