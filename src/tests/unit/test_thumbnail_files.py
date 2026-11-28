"""Where a thumbnail comes from for a downloaded file, the half-block render, and pruning of renders."""

import os

import pytest
from PIL import Image

from src.ui import thumbnail

VID = "abc123def45"


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail, "THUMB_DIR", tmp_path / "thumbs")
    monkeypatch.setattr(thumbnail, "RENDERED_DIR", tmp_path / "rendered")
    return tmp_path


def picture(path):
    Image.new("RGB", (4, 4), (255, 0, 0)).save(path, "JPEG")
    return path


def test_the_indexed_image_is_copied_into_the_cache(dirs):
    own = picture(dirs / "own.jpg")
    found = thumbnail.ensure_thumb_jpeg(VID, {"_thumb_path": str(own)})
    assert found == dirs / "thumbs" / f"{VID}.jpg"
    assert found.read_bytes() == own.read_bytes()


def test_the_image_next_to_the_media_is_used(dirs):
    media = dirs / "clip.mp4"
    media.write_bytes(b"")
    picture(dirs / "clip.jpg")
    assert thumbnail.ensure_thumb_jpeg(VID, {"_local_path": str(media)}) == dirs / "thumbs" / f"{VID}.jpg"


def test_a_failed_copy_falls_back_to_the_source(dirs, monkeypatch):
    media = dirs / "clip.mp4"
    media.write_bytes(b"")
    beside = picture(dirs / "clip.jpg")
    monkeypatch.setattr(thumbnail.shutil, "copy2", lambda *a: (_ for _ in ()).throw(OSError()))
    assert thumbnail.ensure_thumb_jpeg(VID, {"_local_path": str(media)}) == beside
    assert thumbnail.ensure_thumb_jpeg(VID, {"_thumb_path": str(beside)}) == beside


def test_the_render_is_half_blocks_and_cached(dirs):
    picture(dirs / "own.jpg")
    art = thumbnail.render_pil_halfblock(VID, {"_thumb_path": str(dirs / "own.jpg")}, cols=2, rows=1)
    assert art.count("▀") == 2 and art.endswith("\x1b[0m") and "\n" not in art
    assert (dirs / "rendered" / f"{VID}_2x1_pil.ansi").read_text(encoding="utf-8") == art


def test_no_image_renders_nothing(dirs):
    assert thumbnail.render_pil_halfblock("x", {}) == ""
    (dirs / "thumbs").mkdir()
    (dirs / "thumbs" / "x.jpg").write_bytes(b"not an image")
    assert thumbnail.render_pil_halfblock("x", {}) == ""


def test_old_and_surplus_renders_are_pruned(dirs):
    rendered = dirs / "rendered"
    rendered.mkdir()
    for n, age in enumerate((100 * 86400, 30, 20, 10)):
        path = rendered / f"{n}.ansi"
        path.write_text("x", encoding="utf-8")
        stamp = os.path.getmtime(path) - age
        os.utime(path, (stamp, stamp))
    thumbnail.prune_old_rendered(max_age_days=7, max_count=2)
    assert sorted(p.name for p in rendered.iterdir()) == ["2.ansi", "3.ansi"]
