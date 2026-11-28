"""Local listing: one folder, media files as rows, folders as rows to open, hidden and unreadable entries left out."""

import os
import sys

import pytest

from src import local_files


def touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def titles(listing):
    return [e["title"] for e in listing.entries]


def test_lists_parent_then_folders_then_media_files_sorted_and_skips_the_rest(tmp_path):
    root = tmp_path / "root"
    touch(root / "b song.MP3")
    touch(root / "A clip.mkv")
    touch(root / "notes.txt")
    touch(root / ".hidden.mp4")
    (root / "Zeta").mkdir()
    (root / "alpha").mkdir()
    (root / ".git").mkdir()
    listing = local_files.list_folder(root)
    assert titles(listing) == ["..", "alpha", "Zeta", "A clip.mkv", "b song.MP3"]
    parent, alpha = listing.entries[0], listing.entries[1]
    assert parent["_is_folder"] and parent["_local_path"] == str(tmp_path)
    assert alpha["_is_folder"] and alpha["id"].startswith("__dir__")
    clip, song = listing.entries[3], listing.entries[4]
    assert clip["_local_type"] == "video" and song["_local_type"] == "audio"
    assert clip["_local_path"] == str(root / "A clip.mkv") and clip["_size"] == 1
    assert local_files.is_local_id(clip["id"]) and not clip.get("_is_folder")


def test_filesystem_root_has_no_parent_row(tmp_path):
    anchor = os.path.abspath(os.sep)
    listing = local_files.list_folder(anchor, cancelled=lambda: True)
    assert all(e["title"] != ".." for e in listing.entries)


def test_id_changes_when_the_file_changes_so_caches_read_it_again(tmp_path):
    media = touch(tmp_path / "a.mp4", b"one")
    first = local_files.list_folder(tmp_path).entries[-1]["id"]
    media.write_bytes(b"longer content")
    second = local_files.list_folder(tmp_path).entries[-1]["id"]
    assert first != second and local_files.is_local_id(second)
    assert not local_files.is_local_id("dQw4w9WgXcQ") and not local_files.is_local_id("")


def test_unreadable_or_missing_folder_reports_a_reason_instead_of_raising(tmp_path):
    listing = local_files.list_folder(tmp_path / "gone")
    assert listing.error and listing.entries[0]["title"] == ".."


def test_cancelled_listing_stops_early(tmp_path):
    for n in range(5):
        touch(tmp_path / f"{n}.mp3")
    assert [e for e in local_files.list_folder(tmp_path, cancelled=lambda: True).entries if not e["_is_folder"]] == []


@pytest.mark.skipif(sys.platform == "win32", reason="Windows forbids newlines, colons and bars in names")
def test_hostile_names_keep_the_raw_path_but_show_a_clean_title(tmp_path):
    name = "-[bold red]x\nrm -rf ~ https:||evil.mp4"
    media = touch(tmp_path / name)
    entry = local_files.list_folder(tmp_path).entries[-1]
    assert entry["_local_path"] == str(media)
    assert "\n" not in entry["title"] and entry["title"].startswith("-[bold red]x ")


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_symlinked_folder_is_a_row_and_a_loop_cannot_hang_the_listing(tmp_path):
    (tmp_path / "loop").symlink_to(tmp_path)
    touch(tmp_path / "a.mp3")
    listing = local_files.list_folder(tmp_path / "loop")
    assert "loop" in titles(listing) and "a.mp3" in titles(listing)


def test_folder_tracks_are_the_media_files_directly_inside(tmp_path):
    touch(tmp_path / "1.mp3")
    touch(tmp_path / "sub" / "2.mp3")
    touch(tmp_path / "cover.jpg")
    tracks, reason = local_files.folder_tracks(str(tmp_path))
    assert [t["title"] for t in tracks] == ["1.mp3"] and reason == ""
    assert local_files.folder_tracks(str(tmp_path / "empty-none"))[0] == []


def _cwd_gone():
    raise FileNotFoundError


def test_launch_dir_is_captured_once_and_falls_back_to_home(tmp_path, monkeypatch):
    monkeypatch.setattr(local_files, "_launch_dir", None)
    monkeypatch.chdir(tmp_path)
    local_files.capture_launch_dir()
    monkeypatch.chdir(tmp_path.parent)
    assert local_files.launch_dir() == tmp_path.resolve()

    monkeypatch.setattr(local_files, "_launch_dir", None)
    monkeypatch.setattr(local_files.os, "getcwd", _cwd_gone)
    monkeypatch.setattr(local_files.Path, "home", classmethod(lambda cls: tmp_path))
    local_files.capture_launch_dir()
    assert local_files.launch_dir() == tmp_path


def test_main_captures_the_launch_dir_before_anything_else(monkeypatch):
    from src import main

    order = []
    monkeypatch.setattr(local_files, "capture_launch_dir", lambda: order.append("capture"))
    monkeypatch.setattr(main, "_parser", lambda: order.append("parse") or pytest.fail("stop"))
    with pytest.raises(BaseException):
        main.main()
    assert order[:2] == ["capture", "parse"]
