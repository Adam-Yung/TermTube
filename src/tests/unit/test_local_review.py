"""Local files, review round: no mpv references, encodable paths only, clean probe text, MPEG-TS sniffing and more."""

import json

import pytest

from src import history, library, local_files, local_media, player
from src.cache import Cache
from src.tui.screens.watch_command import build_command

_REFS = "--access-references=no"


def test_local_audio_does_not_follow_playlist_references_but_streams_are_unchanged():
    local = player.audio_command("mpv", input_conf="c", socket_path="s", stream_url="/music/song.mp3")
    assert _REFS in local and local[-2:] == ["--", "/music/song.mp3"]
    stream = player.audio_command("mpv", input_conf="c", socket_path="s", stream_url="https://r1.googlevideo.com/x")
    assert _REFS not in stream


def test_local_video_does_not_follow_playlist_references():
    cmd = build_command("mpv", input_conf="c", socket_path="s", title="t", urls=["C:\\v\\hls.mp4"], page_url="",
                        fmt="", cookie_args=[])
    assert _REFS in cmd
    remote = build_command("mpv", input_conf="c", socket_path="s", title="t", urls=["https://x/v", "https://x/a"],
                           page_url="", fmt="", cookie_args=[])
    assert _REFS not in remote


def test_a_path_that_cannot_be_encoded_is_neither_listed_nor_stored(tmp_path, monkeypatch):
    bad = {"id": "local-0123456789abcdef0123", "title": "x", "_local_path": "/m/\udcff.mp3", "_local_type": "audio"}
    record = history.slim(bad, bad["id"])
    assert "_local_path" not in record
    json.dumps(record, ensure_ascii=False).encode("utf-8")
    assert not local_files.encodable("/m/\udcff.mp3") and local_files.encodable("/m/ok é.mp3")


def test_probe_text_drops_terminal_escapes_but_keeps_its_lines(monkeypatch):
    probe = {"format": {"tags": {"title": "a\x1b]52;c;ZXZpbA==\x07b\x1b[2Jc", "artist": "x\ny"}},
             "streams": [{"codec_type": "audio", "codec_name": "fl\x1bac"}]}
    text = local_media._description(probe)
    assert "\x1b" not in text and "\x07" not in text
    assert len(text.splitlines()) == 3


def _ts_file(path, packets):
    path.write_bytes(b"".join(b"\x47" + bytes(187) for _ in range(packets)))


def test_ts_is_video_only_when_it_is_mpeg_ts(tmp_path):
    _ts_file(tmp_path / "movie.ts", 2)
    (tmp_path / "app.ts").write_text("export const x = 1;\n" * 20, encoding="utf-8")
    _ts_file(tmp_path / "short.ts", 1)
    titles = [e["title"] for e in local_files.list_folder(tmp_path).entries]
    assert "movie.ts" in titles and "app.ts" not in titles and "short.ts" not in titles


def test_parent_row_is_flagged(tmp_path):
    assert local_files.list_folder(tmp_path).entries[0]["_is_parent"]


def test_local_ids_never_enter_the_home_suppression_list(tmp_path, monkeypatch):
    monkeypatch.setattr("src.cache._SUPPRESSED_PATH", tmp_path / "suppressed.json")
    cache = Cache({})
    cache.suppress_video("local-0123456789abcdef0123")
    cache.suppress_video("dQw4w9WgXcQ")
    assert cache.is_suppressed("dQw4w9WgXcQ") and not cache.is_suppressed("local-0123456789abcdef0123")


@pytest.mark.parametrize("exists", [True, False])
def test_local_items_of_a_playlist_are_badged_as_on_disk_or_missing(tmp_path, exists):
    media = tmp_path / "a.mp3"
    if exists:
        media.write_bytes(b"a")
    row = {"id": "local-0123456789abcdef0123", "title": "a.mp3", "_local_path": str(media), "_local_type": "audio"}
    shown = library.attach_local([row], [])[0]
    assert "_dl" not in shown and shown["_local_type"] == "audio"
    assert bool(shown.get("_missing_file")) is (not exists)
