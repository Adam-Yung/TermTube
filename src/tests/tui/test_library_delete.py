"""Library tab: D asks what exactly goes (with sizes), deletes files outright, and u cannot bring them back."""

import json
from unittest.mock import patch

import pytest

from src import history, library
from src.tui.library_delete import ask
from src.tui.widgets.video_list import VideoListItem, VideoListPanel


@pytest.fixture(autouse=True)
def no_detail_network(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)


def add(directory, vid, upload_date, ext="mp4", size=5):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{vid}.{ext}").write_bytes(b"x" * size)
    sidecar = {"id": vid, "title": f"Title {vid}", "upload_date": upload_date, "formats": [{"url": "u"}]}
    (directory / f"{vid}.info.json").write_text(json.dumps(sidecar), encoding="utf-8")


@pytest.fixture
def lib(app, tmp_path):
    videos, audio = tmp_path / "vid", tmp_path / "aud"
    add(videos, "a1", "20260103")
    add(videos, "b2", "20260102", size=2000)
    add(audio, "b2", "20260102", ext="mp3", size=40)
    add(videos, "c3", "20260101")
    app.config._data["video_dir"], app.config._data["audio_dir"] = str(videos), str(audio)
    return videos, audio


def panel_of(app) -> VideoListPanel:
    return app.screen.query_one("#video-list-panel", VideoListPanel)


def ids(app):
    return [c.entry["id"] for c in panel_of(app)._lv.children if isinstance(c, VideoListItem)]


async def open_library(app, pilot):
    await pilot.pause(0.8)
    await pilot.press("f5")
    await pilot.pause(0.6)


async def test_question_names_forms_with_sizes_and_b_deletes_both_for_good(app, lib):
    videos, audio = lib
    async with app.run_test(size=(120, 40)) as pilot:
        await open_library(app, pilot)
        assert ids(app) == ["a1", "b2", "c3"]
        await pilot.press("j", "D")
        await pilot.pause(0.1)
        targets, choices = app.screen._pending_remove
        assert targets[0]["id"] == "b2" and set(choices) == {"v", "a", "b", "e"}
        await pilot.press("b")
        await pilot.pause(0.4)
        assert ids(app) == ["a1", "c3"]
        assert not (videos / "b2.mp4").exists() and not (audio / "b2.mp3").exists()
        assert (videos / "a1.mp4").exists()
        await pilot.press("u")
        await pilot.pause(0.2)
        assert ids(app) == ["a1", "c3"] and app.screen._undo is None


async def test_marked_rows_ask_once_and_other_keys_cancel(app, lib):
    videos, _ = lib
    async with app.run_test(size=(120, 40)) as pilot:
        await open_library(app, pilot)
        await pilot.press("m", "m", "D")
        await pilot.pause(0.1)
        targets, choices = app.screen._pending_remove
        assert [t["id"] for t in targets] == ["a1", "b2"] and choices == {"y": "both"}
        await pilot.press("n")
        await pilot.pause(0.1)
        assert (videos / "a1.mp4").exists() and ids(app) == ["a1", "b2", "c3"]
        await pilot.press("D", "y")
        await pilot.pause(0.4)
        assert ids(app) == ["c3"] and not (videos / "a1.mp4").exists() and not (videos / "b2.mp4").exists()


async def test_missing_file_row_is_flagged_blocks_play_and_removes_the_entry(app, lib):
    videos, _ = lib
    (videos / "a1.mp4").unlink()
    async with app.run_test(size=(120, 40)) as pilot:
        await open_library(app, pilot)
        row = next(c for c in panel_of(app)._lv.children if isinstance(c, VideoListItem))
        assert row.entry["_missing_file"] and "file missing" in row._build_markup()
        with patch.object(app.screen, "_watch") as watch:
            await pilot.press("v")
            await pilot.pause(0.1)
        assert not watch.called
        await pilot.press("D")
        await pilot.pause(0.1)
        assert app.screen._pending_remove[1] == {"y": "entry_only"}
        await pilot.press("y")
        await pilot.pause(0.4)
        assert ids(app) == ["b2", "c3"] and not (videos / "a1.info.json").exists()


def test_question_text_has_sizes(lib):
    videos, audio = lib
    entries = {e["id"]: e for e in library.all_entries(videos, audio)}
    text, choices = ask([entries["b2"]])
    assert "video 2.0 KB + audio 40 B" in text and "entry only" in text and len(choices) == 4
    text, choices = ask([entries["a1"]])
    assert "video 5 B" in text and choices == {"y": "both"}
    assert "Delete 2 items (2.0 KB)" in ask([entries["a1"], entries["b2"]])[0]


def test_history_stays_slim_when_a_library_row_is_played(lib, temp_history):
    videos, audio = lib
    entry = library.all_entries(videos, audio)[1]
    history.add(entry)
    saved = history.all_entries()[0]
    assert not any(k.startswith("_") or k in ("formats", "description", "tags") for k in saved)
