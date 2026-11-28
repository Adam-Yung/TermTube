"""Local file details and thumbnails: managed tools only, the right ffprobe fields, cover art before a frame."""

import json
import os
import subprocess
from functools import partial
from types import SimpleNamespace

import pytest

from src import local_files, local_media

_PROBE = {
    "format": {"duration": "5.2", "bit_rate": "3200000", "tags": {"artist": "Ada", "album": "Tapes", "title": "Song"}},
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
         "avg_frame_rate": "30/1", "disposition": {"attached_pic": 0}},
        {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000"},
        {"index": 2, "codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
    ],
}


def _fake_run(calls, cmd, **kwargs):
    calls.append(cmd)
    if "ffprobe" in os.path.basename(cmd[0]):
        return SimpleNamespace(returncode=0, stdout=json.dumps(_PROBE).encode())
    with open(cmd[-1].removeprefix("file:"), "wb") as out:
        out.write(b"jpeg")
    return SimpleNamespace(returncode=0, stdout=b"")


def _hang(cmd, **kwargs):
    raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))


@pytest.fixture
def tools(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("ffprobe", "ffmpeg"):
        (bin_dir / name).write_bytes(b"")
        (bin_dir / f"{name}.exe").write_bytes(b"")
    monkeypatch.setattr(local_media, "get_deps_bin", lambda: bin_dir)
    local_media.clear_cache()
    calls = []
    monkeypatch.setattr(local_media.subprocess, "run", partial(_fake_run, calls))
    return calls


def media_row(tmp_path, name="-a:b.mp4"):
    (tmp_path / name).write_bytes(b"x")
    return next(e for e in local_files.list_folder(tmp_path).entries if e["title"] == name)


def test_details_read_duration_streams_and_tags(tmp_path, tools):
    fields = local_media.details(media_row(tmp_path))
    assert fields["duration"] == 5
    for part in ("h264", "1920×1080", "30 fps", "aac", "2 ch", "48 kHz", "Ada", "Tapes", "Song", "3.2 Mb/s"):
        assert part in fields["description"]


def test_tools_get_the_path_as_a_file_url_after_their_options(tmp_path, tools):
    entry = media_row(tmp_path)
    local_media.details(entry)
    local_media.details(entry)
    assert len(tools) == 1, "the second call is answered from the cache"
    assert tools[0][0].startswith(str(tmp_path / "bin")) and tools[0][-1] == "file:" + entry["_local_path"]


def test_cover_art_is_used_before_a_frame(tmp_path, tools):
    dest = tmp_path / "thumbs" / "t.jpg"
    assert local_media.thumbnail(media_row(tmp_path), dest) == dest
    extract = tools[-1]
    assert extract[extract.index("-map") + 1] == "0:2" and "-ss" not in extract


def test_a_frame_at_3_s_or_half_a_short_file(tmp_path, tools, monkeypatch):
    _PROBE_NO_COVER = {**_PROBE, "streams": _PROBE["streams"][:2]}
    for duration, at in (("5.2", "3"), ("1.0", "0.5")):
        probe = {**_PROBE_NO_COVER, "format": {"duration": duration}}
        monkeypatch.setattr(local_media, "_probe", lambda path, p=probe: p)
        dest = tmp_path / f"{duration}.jpg"
        assert local_media.thumbnail(media_row(tmp_path, f"{duration}.mp4"), dest) == dest
        extract = tools[-1]
        assert extract[extract.index("-ss") + 1] == at


def test_audio_without_cover_has_no_thumbnail(tmp_path, tools, monkeypatch):
    monkeypatch.setattr(local_media, "_probe", lambda path: {"format": {}, "streams": [_PROBE["streams"][1]]})
    assert local_media.thumbnail(media_row(tmp_path, "a.mp3"), tmp_path / "t.jpg") is None


def test_without_managed_tools_nothing_runs_even_if_path_has_them(tmp_path, monkeypatch):
    monkeypatch.setattr(local_media, "get_deps_bin", lambda: tmp_path / "empty")
    monkeypatch.setattr(local_media.subprocess, "run", lambda *a, **k: pytest.fail("ran a tool"))
    local_media.clear_cache()
    entry = media_row(tmp_path)
    assert local_media.thumbnail(entry, tmp_path / "t.jpg") is None
    assert local_media.details(entry)["description"] == local_media.text("local_media.no_ffprobe")


def test_a_failing_or_hanging_probe_gives_an_empty_answer(tmp_path, tools, monkeypatch):
    monkeypatch.setattr(local_media.subprocess, "run", _hang)
    assert local_media.details(media_row(tmp_path))["description"] == local_media.text("local_media.unreadable")
