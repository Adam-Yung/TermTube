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
    sidecar = {"id": vid, "title": vid, "upload_date": upload_date}
    (directory / f"{vid}.info.json").write_text(json.dumps(sidecar), encoding="utf-8")


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
    monkeypatch.setattr(library, "_scan_root", lambda *a: pytest.fail("rescanned"))
    assert library.all_entries(videos, audio) is first


def test_missing_directories_are_empty(tmp_path):
    assert library.all_entries(tmp_path / "none", tmp_path / "also-none") == []


# ── index: incremental refresh, robustness ──────────────────────────────────────────────────────────────────────


def parsed_ids(monkeypatch):
    """Record which sidecars `_parse` reads from here on."""
    seen = []
    real = library._parse
    monkeypatch.setattr(library, "_parse", lambda path, *a: seen.append(os.path.basename(path)) or real(path, *a))
    return seen


def test_rebuild_parses_only_new_or_changed_sidecars(tmp_path, monkeypatch):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    add_video(videos, "one")
    add_video(videos, "two")
    library.all_entries(videos, audio)
    seen = parsed_ids(monkeypatch)
    add_video(videos, "three")
    bump(videos, 5)
    library.invalidate_cache()
    assert len(library.all_entries(videos, audio)) == 3
    assert seen == ["three.info.json"]
    (videos / "one.info.json").write_text(json.dumps({"id": "one", "title": "renamed"}), encoding="utf-8")
    library.invalidate_cache()
    titles = {e["id"]: e["title"] for e in library.all_entries(videos, audio)}
    assert titles["one"] == "renamed" and seen == ["three.info.json", "one.info.json"]


def test_index_survives_a_restart_and_forgets_deleted_files(tmp_path, monkeypatch):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    add_video(videos, "one")
    add_video(videos, "two")
    library.all_entries(videos, audio)
    library._index.flush()
    library._index._data = None  # a new process reads the file again
    seen = parsed_ids(monkeypatch)
    library.invalidate_cache()
    assert len(library.all_entries(videos, audio)) == 2 and seen == []
    (videos / "two.info.json").unlink()
    (videos / "two.mp4").unlink()
    bump(videos, 5)
    assert [e["id"] for e in library.all_entries(videos, audio)] == ["one"]
    assert list(library._index.read(dict)) == [str(videos / "one.info.json")]


def test_index_is_slim(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    videos.mkdir()
    sidecar = {"id": "x", "title": "T", "description": "d" * 900, "formats": [{"url": "u"}] * 50, "tags": ["a"]}
    (videos / "x.info.json").write_text(json.dumps(sidecar), encoding="utf-8")
    (videos / "x.mp4").write_bytes(b"x")
    entry = library.all_entries(videos, audio)[0]
    assert "formats" not in entry and len(entry["description"]) == 500 and entry["tags"] == ["a"]
    assert entry["_size"] == 1 and entry["_sidecar_path"].endswith("x.info.json")


def test_corrupt_sidecar_is_skipped(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    add_video(videos, "good")
    (videos / "bad.info.json").write_text("{not json", encoding="utf-8")
    (videos / "noid.info.json").write_text("{}", encoding="utf-8")
    assert [e["id"] for e in library.all_entries(videos, audio)] == ["good"]


def test_media_without_sidecar_is_not_listed_and_sidecar_without_media_is_flagged(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    videos.mkdir()
    (videos / "orphan.mp4").write_bytes(b"x")
    (videos / "ghost.info.json").write_text(json.dumps({"id": "ghost"}), encoding="utf-8")
    entries = library.all_entries(videos, audio)
    assert [e["id"] for e in entries] == ["ghost"]
    assert entries[0]["_missing_file"] is True and "_local_path" not in entries[0]


def test_video_and_audio_merge_with_sizes_and_audio_only_entries(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    add_video(videos, "both")
    add_video(audio, "both")
    (audio / "both.mp4").unlink()
    (audio / "both.mp3").write_bytes(b"xyz")
    add_video(audio, "song")
    (audio / "song.mp4").unlink()
    (audio / "song.mp3").write_bytes(b"xy")
    by_id = {e["id"]: e for e in library.all_entries(videos, audio)}
    both, song = by_id["both"], by_id["song"]
    assert both["_has_audio"] and both["_audio_path"].endswith("both.mp3") and both["_audio_size"] == 3
    assert song["_local_type"] == "audio" and song["_size"] == 2 and "_has_audio" not in song
    assert library.total_size(both) == 4


def test_refresh_indexes_one_finished_download(tmp_path, monkeypatch):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    add_video(videos, "one")
    library.all_entries(videos, audio)
    add_video(videos, "two")
    seen = parsed_ids(monkeypatch)
    library.refresh([videos / "two.mp4", videos / "two.f137.mp4"])
    assert seen == ["two.info.json"]
    assert {e["id"] for e in library.all_entries(videos, audio)} == {"one", "two"}
    assert seen == ["two.info.json"]  # the rebuild reused the record


# ── safe_delete ─────────────────────────────────────────────────────────────────────────────────────────────────


def full_entry(tmp_path, vid="v1"):
    videos, audio = tmp_path / "v", tmp_path / "a"
    add_video(videos, vid)
    (videos / f"{vid}.jpg").write_bytes(b"i")
    (videos / f"{vid}.en.vtt").write_bytes(b"s")
    (videos / f"{vid}2.mp4").write_bytes(b"other")  # a different video that must survive
    add_video(audio, vid)
    (audio / f"{vid}.mp4").unlink()
    (audio / f"{vid}.mp3").write_bytes(b"aa")
    entry = next(e for e in library.all_entries(videos, audio) if e["id"] == vid)
    return entry, [videos, audio]


def test_delete_video_leaves_audio_and_neighbours(tmp_path):
    entry, roots = full_entry(tmp_path)
    result = library.safe_delete(entry, roots, "video")
    names = {os.path.basename(p) for p in result.removed}
    assert names == {"v1.mp4", "v1.info.json", "v1.jpg", "v1.en.vtt"} and not result.failed
    assert (tmp_path / "v" / "v12.mp4").exists() and (tmp_path / "a" / "v1.mp3").exists()
    left = library.all_entries(*roots)
    assert [e["id"] for e in left] == ["v1"] and left[0]["_local_type"] == "audio"


def test_delete_both_and_no_entry_only_choice(tmp_path):
    entry, roots = full_entry(tmp_path)
    with pytest.raises(ValueError):
        library.safe_delete(entry, roots, "entry_only")
    assert (tmp_path / "v" / "v1.mp4").exists()
    entry, roots = full_entry(tmp_path, "v3")
    result = library.safe_delete(entry, roots, "both")
    assert result.freed >= 3
    assert not (tmp_path / "a" / "v3.mp3").exists() and not (tmp_path / "v" / "v3.mp4").exists()


def test_delete_missing_file_entry_removes_sidecar_and_never_raises(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    videos.mkdir()
    (videos / "g.info.json").write_text(json.dumps({"id": "g"}), encoding="utf-8")
    entry = library.all_entries(videos, audio)[0]
    (videos / "g.info.json").unlink()  # already gone
    result = library.safe_delete(entry, [videos, audio], "both")
    assert result.removed == [] and result.failed == []


def test_delete_refuses_symlinks_dotdot_and_outside_paths(tmp_path):
    videos, audio, outside = tmp_path / "v", tmp_path / "a", tmp_path / "out"
    audio.mkdir()
    outside.mkdir()
    victim = outside / "precious.mp4"
    victim.write_bytes(b"keep")
    add_video(videos, "s")
    (videos / "s.mp4").unlink()
    (videos / "s.mp4").symlink_to(victim)
    entry = {"id": "s", "_local_type": "video", "_local_path": str(videos / "s.mp4"),
             "_sidecar_path": str(videos / "s.info.json")}
    result = library.safe_delete(entry, [videos, audio], "video")
    assert victim.exists() and any("symbolic link" in why for _, why in result.failed)
    for evil in (str(videos / ".." / "out" / "precious.mp4"), str(victim)):
        entry = {"id": "s", "_local_type": "video", "_local_path": evil, "_sidecar_path": None}
        result = library.safe_delete(entry, [videos, audio], "video")
        assert victim.exists() and result.removed == [] and result.failed
    linked_dir = videos / "linkdir"
    linked_dir.symlink_to(outside)
    entry = {"id": "s", "_local_type": "video", "_local_path": str(linked_dir / "precious.mp4"), "_sidecar_path": None}
    assert library.safe_delete(entry, [videos, audio], "video").removed == [] and victim.exists()


def test_delete_ignores_a_sidecar_claiming_a_path_elsewhere(tmp_path):
    videos, audio = tmp_path / "v", tmp_path / "a"
    audio.mkdir()
    victim = tmp_path / "precious.mp4"
    victim.write_bytes(b"keep")
    videos.mkdir()
    sidecar = {"id": "c", "_local_path": str(victim), "_audio_path": str(victim), "_has_audio": True}
    (videos / "c.info.json").write_text(json.dumps(sidecar), encoding="utf-8")
    (videos / "c.mp4").write_bytes(b"x")
    entry = library.all_entries(videos, audio)[0]
    assert entry["_local_path"] == str(videos / "c.mp4") and "_has_audio" not in entry
    library.safe_delete(entry, [videos, audio], "both")
    assert victim.exists()


def test_shared_stem_in_one_folder_keeps_the_other_forms_sidecar(tmp_path):
    folder = tmp_path / "all"
    folder.mkdir()
    (folder / "x.mp4").write_bytes(b"v")
    (folder / "x.info.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    other = tmp_path / "empty"
    other.mkdir()
    entry = library.all_entries(folder, other)[0]
    (folder / "x.mp3").write_bytes(b"a")
    result = library.safe_delete(entry, [folder], "video")
    assert [os.path.basename(p) for p in result.removed] == ["x.mp4"] and (folder / "x.info.json").exists()


def test_normalise_thumbnail_converts_webp_to_jpeg(tmp_path):
    from PIL import Image

    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    Image.new("RGB", (4, 4), "red").save(tmp_path / "clip.webp", "WEBP")
    jpg = library.normalise_thumbnail(media)
    assert jpg == tmp_path / "clip.jpg" and Image.open(jpg).format == "JPEG" and not (tmp_path / "clip.webp").exists()
    assert library.normalise_thumbnail(tmp_path / "none.mp4") is None
