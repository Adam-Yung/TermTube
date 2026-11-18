"""The playlist modal never resets an existing playlist and pins the entry it was opened with."""

from textual.widgets import Input

from src import playlist
from src.tui.screens.playlist_modal import PlaylistModal

ENTRY = {"id": "abc123def45", "title": "A video", "uploader": "Chan", "formats": [{"format_id": "18"}]}


async def test_new_name_that_exists_is_rejected(app, temp_playlists):
    playlist.create("Mix", [{"id": "old00000001", "title": "Old"}])
    async with app.run_test(size=(100, 30)) as pilot:
        notes = []
        app.notify = lambda msg, **kw: notes.append((msg, kw.get("severity")))
        app.push_screen(PlaylistModal(ENTRY))
        await pilot.pause(0.2)
        field = app.screen.query_one("#playlist-new-input", Input)
        field.value = "Mix"
        await field.action_submit()
        await pilot.pause(0.1)
        assert [i["id"] for i in playlist.find_by_name("Mix")["items"]] == ["old00000001"]
        assert notes == [('Playlist "Mix" already exists', "warning")]


async def test_adding_pins_the_entry_without_fat_fields(app, temp_playlists):
    async with app.run_test(size=(100, 30)) as pilot:
        app.push_screen(PlaylistModal(ENTRY))
        await pilot.pause(0.2)
        field = app.screen.query_one("#playlist-new-input", Input)
        field.value = "Fresh"
        await field.action_submit()
        await pilot.pause(0.1)
        assert [i["id"] for i in playlist.find_by_name("Fresh")["items"]] == ["abc123def45"]
        pinned = app.cache.get_video_raw("abc123def45")
        assert pinned["title"] == "A video"
        assert "formats" not in pinned
