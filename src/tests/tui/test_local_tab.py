"""The Local tab (F6): the launch folder as rows, folders open in place, files play, D deletes one file, no YouTube."""

import threading
import time
from functools import partial
from unittest.mock import patch

import pytest

from src import local_files, local_media, player
from src.tests.fakes import silence_detail_workers
from src.tests.tui.waits import settle, until
from src.tui.widgets.video_list import VideoListItem, VideoListPanel


@pytest.fixture
def folder(tmp_path, monkeypatch):
    root = tmp_path / "start"
    (root / "Albums").mkdir(parents=True)
    (root / "Albums" / "track.mp3").write_bytes(b"t")
    (root / "clip.mp4").write_bytes(b"c" * 10)
    (root / "song.flac").write_bytes(b"s")
    (root / "readme.txt").write_bytes(b"x")
    monkeypatch.setattr(local_files, "_launch_dir", root)
    return root


def panel_of(app) -> VideoListPanel:
    return app.screen.query_one("#video-list-panel", VideoListPanel)


def titles(app):
    return [c.entry["title"] for c in panel_of(app)._lv.children if isinstance(c, VideoListItem)]


def highlighted(app):
    return panel_of(app).selected_entry


async def open_local(app, pilot):
    await pilot.pause(0.5)
    await pilot.press("f6")
    await until(pilot, lambda: "clip.mp4" in titles(app) or "track.mp3" in titles(app))


async def goto(app, pilot, title):
    await pilot.press("g")
    for _ in range(len(titles(app))):
        await pilot.pause(0.05)
        if (highlighted(app) or {}).get("title") == title:
            return
        await pilot.press("j")
    raise AssertionError(f"no row {title!r} in {titles(app)}")


async def test_f6_lists_the_launch_folder_and_folders_open_and_close_in_place(app, folder, monkeypatch):
    silence_detail_workers(monkeypatch)
    async with app.run_test(size=(120, 40)) as pilot:
        await open_local(app, pilot)
        assert app.screen._current_tab == "local"
        assert titles(app) == ["..", "Albums", "clip.mp4", "song.flac"]
        await goto(app, pilot, "Albums")
        await pilot.press("enter")
        await until(pilot, lambda: titles(app) == ["..", "track.mp3"])
        await pilot.press("backspace")
        await until(pilot, lambda: "clip.mp4" in titles(app))
        await until(pilot, lambda: highlighted(app)["title"] == "Albums")
        await goto(app, pilot, "..")
        await pilot.press("enter")
        await until(pilot, lambda: "start" in titles(app))


async def test_d_deletes_only_the_chosen_file_after_one_yes_and_never_a_folder(app, folder, monkeypatch):
    silence_detail_workers(monkeypatch)
    async with app.run_test(size=(120, 40)) as pilot:
        await open_local(app, pilot)
        await goto(app, pilot, "clip.mp4")
        await pilot.press("D")
        await pilot.pause(0.05)
        assert app.screen._pending_remove is not None
        await pilot.press("y")
        await until(pilot, lambda: "clip.mp4" not in titles(app))
        assert not (folder / "clip.mp4").exists() and (folder / "song.flac").exists()
        await goto(app, pilot, "Albums")
        await pilot.press("D")
        await pilot.pause(0.05)
        await pilot.press("y")
        await settle(app, pilot)
        assert (folder / "Albums" / "track.mp3").exists() and "Albums" in titles(app)


async def test_files_play_from_disk_and_a_folder_row_plays_its_files(app, folder, monkeypatch):
    silence_detail_workers(monkeypatch)
    async with app.run_test(size=(120, 40)) as pilot:
        await open_local(app, pilot)
        with patch.object(app.audio, "play_audio") as play_one, patch.object(app.audio, "play_many") as play_many:
            await goto(app, pilot, "song.flac")
            await pilot.press("a")
            assert play_one.call_args.args[0]["_local_path"] == str(folder / "song.flac")
            await goto(app, pilot, "Albums")
            await pilot.press("a")
            await until(pilot, lambda: play_many.called)
        assert [t["title"] for t in play_many.call_args.args[0]] == ["track.mp3"]


async def test_youtube_actions_answer_with_a_reason_and_are_hidden_from_the_menu(app, folder, monkeypatch):
    silence_detail_workers(monkeypatch)
    monkeypatch.setattr("webbrowser.open", lambda *a: pytest.fail("opened a browser for a local file"))
    monkeypatch.setattr("src.tui.screens.mixins.item_actions.clipboard_copy", lambda *a: pytest.fail("copied"))
    async with app.run_test(size=(120, 40)) as pilot:
        await open_local(app, pilot)
        await goto(app, pilot, "clip.mp4")
        screen = app.screen
        with patch.object(screen, "notify") as notify:
            for key in ("d", "c", "y", "b"):
                screen.__dict__.pop("_hint_times", None)
                await pilot.press(key)
                assert "local file" in notify.call_args.args[0]
        assert len(app.screen_stack) == 2
        hidden = screen._hidden_menu_actions(highlighted(app))
        assert {"download", "channel", "copy_url", "browser", "watch_quality", "audio_quality"} <= hidden


async def test_highlighting_a_file_probes_it_locally_and_fills_the_detail_panel(app, folder, monkeypatch):
    monkeypatch.setattr("src.innertube.fetch_video_details", lambda *a, **k: pytest.fail("asked YouTube"))
    monkeypatch.setattr(local_media, "details", lambda entry: {"duration": 75, "description": "Video: probe ok"})
    monkeypatch.setattr(local_media, "thumbnail", lambda entry, dest: None)
    async with app.run_test(size=(120, 40)) as pilot:
        await open_local(app, pilot)
        await goto(app, pilot, "clip.mp4")
        await until(pilot, lambda: (highlighted(app) or {}).get("duration") == 75)
        # the row and the panel are updated by two separate calls from the worker
        await until(pilot, lambda: "probe ok" in str(app.screen.query_one("#video-desc").render()))


def _record_run(seen, build_cmd, **kwargs):
    seen.append(build_cmd(1))
    return player.MpvOutcome("killed")


async def test_a_local_row_without_a_path_never_reaches_mpv_or_youtube(app):
    seen, done = [], threading.Event()
    with patch.object(player, "run_mpv_with_retries", partial(_record_run, seen)), \
            patch("src.streams.resolve_for_playback", side_effect=AssertionError("resolved a local id")):
        async with app.run_test(size=(100, 30)) as pilot:
            with patch.object(app, "notify", side_effect=lambda *a, **k: done.set()):
                app.audio.play_audio({"id": "local-0123456789abcdef0123", "title": "gone.mp3"})
                await until(pilot, done.is_set)
    assert seen == []


async def test_marked_folders_are_not_delete_targets(app, folder, monkeypatch):
    silence_detail_workers(monkeypatch)
    async with app.run_test(size=(120, 40)) as pilot:
        await open_local(app, pilot)
        with patch.object(app.screen, "notify") as notify:
            await pilot.press("M", "D")
            await pilot.pause(0.05)
            targets, _ = app.screen._pending_remove
            assert sorted(t["title"] for t in targets) == ["clip.mp4", "song.flac"]
            await pilot.press("y")
            await until(pilot, lambda: notify.called)
        message = notify.call_args.args[0]
        assert "2" in message and "could not" not in message
        assert (folder / "Albums" / "track.mp3").exists()


def _slow_listing(real, *args, **kwargs):
    time.sleep(0.4)
    return real(*args, **kwargs)


async def test_two_quick_backspaces_go_up_two_folders(app, folder, monkeypatch):
    silence_detail_workers(monkeypatch)
    (folder / "Albums" / "Deep").mkdir()
    monkeypatch.setattr(local_files, "_launch_dir", folder / "Albums" / "Deep")
    monkeypatch.setattr(local_files, "list_folder", partial(_slow_listing, local_files.list_folder))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        await pilot.press("f6")
        await until(pilot, lambda: titles(app) == [".."])
        await pilot.press("backspace", "backspace")
        await until(pilot, lambda: "clip.mp4" in titles(app))
        assert app.screen._local_dir == folder


async def test_folder_rows_show_the_placeholder_not_loading(app, folder, monkeypatch):
    silence_detail_workers(monkeypatch)
    states = []
    monkeypatch.setattr("src.tui.widgets.thumbnail_widget.ThumbnailWidget.set_loading",
                        lambda self: states.append("loading"))
    monkeypatch.setattr("src.tui.widgets.thumbnail_widget.ThumbnailWidget.set_placeholder",
                        lambda self: states.append("placeholder"))
    async with app.run_test(size=(120, 40)) as pilot:
        await open_local(app, pilot)
        await goto(app, pilot, "Albums")
        await pilot.pause(0.3)
        assert states[-1] == "placeholder"


async def test_the_parent_row_is_not_played_and_quality_keys_answer_with_a_reason(app, folder, monkeypatch):
    silence_detail_workers(monkeypatch)
    async with app.run_test(size=(120, 40)) as pilot:
        await open_local(app, pilot)
        screen = app.screen
        await goto(app, pilot, "..")
        hints = [label for _key, label in screen.panel_hints()]
        assert "Queue" not in hints
        with patch.object(app.audio, "play_many") as play_many, patch.object(screen, "notify") as notify:
            await pilot.press("a")
            await settle(app, pilot)
            assert not play_many.called and notify.called
            await goto(app, pilot, "clip.mp4")
            for key in ("V", "A"):
                screen.__dict__.pop("_hint_times", None)
                await pilot.press(key)
                assert "local file" in notify.call_args.args[0]
        assert len(app.screen_stack) == 2
