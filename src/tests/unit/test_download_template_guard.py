"""A filename template or a title must not move a download outside the configured directory."""

from pathlib import Path

import pytest
import yt_dlp

from src.downloads import _outtmpl, _StayInside


@pytest.mark.parametrize("template", [
    "../%(title)s.%(ext)s",
    "a/../../%(title)s.%(ext)s",
    "a\\..\\b.%(ext)s",
    "/etc/%(title)s.%(ext)s",
    "\\\\server\\share\\%(title)s.%(ext)s",
    "C:\\Users\\x\\%(title)s.%(ext)s",
    "",
])
def test_unsafe_templates_are_rejected(tmp_path, template):
    with pytest.raises(RuntimeError, match="Unsafe download template"):
        _outtmpl(tmp_path, template)


@pytest.mark.parametrize("template", [
    "%(title)s_%(uploader)s.%(ext)s",
    "%(uploader)s/%(title)s.%(ext)s",
    "v..1/%(title)s.%(ext)s",
])
def test_relative_templates_stay_under_the_directory(tmp_path, template):
    assert _outtmpl(tmp_path, template) == str(tmp_path / template)


def _guard(root: Path, template: str):
    ydl = yt_dlp.YoutubeDL({"outtmpl": str(root / template), "quiet": True})
    return _StayInside(ydl, root)


def test_a_title_of_dots_cannot_climb_out(tmp_path):
    root = tmp_path / "videos"
    root.mkdir()
    guard = _guard(root, "%(title)s/%(id)s.%(ext)s")
    with pytest.raises(yt_dlp.utils.DownloadError, match="outside"):
        guard.run({"id": "abc123def45", "title": "..", "ext": "mp4", "epoch": 1})


def test_an_ordinary_title_passes(tmp_path):
    root = tmp_path / "videos"
    root.mkdir()
    guard = _guard(root, "%(title)s/%(id)s.%(ext)s")
    info = {"id": "abc123def45", "title": "Nice video", "ext": "mp4", "epoch": 1}
    assert guard.run(dict(info)) == ([], info)
