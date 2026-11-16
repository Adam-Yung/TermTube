"""library.all_entries: sidecar scan and cache invalidation."""

import json
import os

import pytest

from src import library


@pytest.fixture(autouse=True)
def fresh_cache():
    library.invalidate_cache()
    yield
    library.invalidate_cache()


def add_video(directory, vid, upload_date="20260101"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{vid}.mp4").write_bytes(b"x")
    (directory / f"{vid}.info.json").write_text(json.dumps({"id": vid, "title": vid, "upload_date": upload_date}))


def bump(path, seconds):
    """Move a directory's mtime forward so the test does not depend on filesystem timestamp resolution."""
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + seconds))


def test_lists_videos_with_local_paths_newest_first(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    add_video(videos, "old", "20250101")
    add_video(videos, "new", "20260101")
    entries = library.all_entries(videos, audio)
    assert [e["id"] for e in entries] == ["new", "old"]
    assert entries[0]["_local_type"] == "video" and entries[0]["_local_path"].endswith("new.mp4")


def test_a_file_added_in_a_subfolder_is_seen_without_invalidating(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    add_video(videos / "channel", "first")
    assert [e["id"] for e in library.all_entries(videos, audio)] == ["first"]
    add_video(videos / "channel", "second")
    bump(videos / "channel", 5)
    assert {e["id"] for e in library.all_entries(videos, audio)} == {"first", "second"}


def test_a_new_subfolder_is_seen(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    add_video(videos, "top")
    library.all_entries(videos, audio)
    add_video(videos / "deep" / "er", "nested")
    bump(videos, 5)
    assert {e["id"] for e in library.all_entries(videos, audio)} == {"top", "nested"}


def test_unchanged_directories_are_served_from_the_cache(tmp_path, monkeypatch):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    add_video(videos, "one")
    first = library.all_entries(videos, audio)
    monkeypatch.setattr(library, "_scan_dir", lambda *a: pytest.fail("rescanned"))
    assert library.all_entries(videos, audio) is first


def test_missing_directories_are_empty(tmp_path):
    assert library.all_entries(tmp_path / "none", tmp_path / "also-none") == []
