"""Local `D`: only the chosen file goes; never a folder, never a link's target, never a file changed since listing."""

import sys

import pytest

from src import local_files


def row(folder, name):
    return next(e for e in local_files.list_folder(folder).entries if e["title"] == name)


def test_deletes_only_the_chosen_file(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"a")
    (tmp_path / "a.jpg").write_bytes(b"j")
    (tmp_path / "b.mp4").write_bytes(b"b")
    assert local_files.delete_file(row(tmp_path, "a.mp4")) is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.jpg", "b.mp4"]


def test_refuses_folders_and_rows_without_a_path(tmp_path):
    (tmp_path / "sub").mkdir()
    assert local_files.delete_file(row(tmp_path, "sub"))
    assert (tmp_path / "sub").is_dir()
    assert local_files.delete_file({"id": "local-x", "title": "t"})


def test_refuses_a_file_that_changed_or_became_a_folder(tmp_path):
    media = tmp_path / "a.mp4"
    media.write_bytes(b"a")
    entry = row(tmp_path, "a.mp4")
    media.write_bytes(b"rewritten")
    assert local_files.delete_file(entry)
    assert media.exists()
    media.unlink()
    media.mkdir()
    assert local_files.delete_file(entry)
    assert media.is_dir()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_a_symlink_row_removes_the_link_and_keeps_its_target(tmp_path):
    target = tmp_path / "keep" / "real.mp3"
    target.parent.mkdir()
    target.write_bytes(b"music")
    shown = tmp_path / "shown"
    shown.mkdir()
    (shown / "link.mp3").symlink_to(target)
    assert local_files.delete_file(row(shown, "link.mp3")) is None
    assert target.read_bytes() == b"music" and not (shown / "link.mp3").exists()


def test_missing_file_is_reported(tmp_path):
    media = tmp_path / "a.mp4"
    media.write_bytes(b"a")
    entry = row(tmp_path, "a.mp4")
    media.unlink()
    assert local_files.delete_file(entry)
