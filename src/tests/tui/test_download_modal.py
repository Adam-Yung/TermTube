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
