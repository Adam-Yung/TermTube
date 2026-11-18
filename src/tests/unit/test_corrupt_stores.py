"""A damaged user file starts empty, leaves a `.bad` copy and never crashes the caller."""

from src import history, library, playlist, search_history

GARBAGE = "{not json"


def test_corrupt_search_history_starts_empty(temp_search_history):
    temp_search_history.write_text(GARBAGE, encoding="utf-8")
    assert search_history.all_queries() == []
    search_history.add("cats")
    assert search_history.all_queries() == ["cats"]
    assert temp_search_history.with_name("search_history.json.bad").read_text(encoding="utf-8") == GARBAGE


def test_corrupt_history_starts_empty(temp_history):
    temp_history.write_text(GARBAGE, encoding="utf-8")
    assert history.all_entries() == []
    assert temp_history.with_name("history.json.bad").exists()


def test_corrupt_library_index_is_rebuilt_from_the_sidecars(tmp_path, monkeypatch):
    index = tmp_path / "idx" / "library.json"
    index.parent.mkdir()
    index.write_text(GARBAGE, encoding="utf-8")
    monkeypatch.setattr("src.library.INDEX_PATH", index)
    monkeypatch.setattr("src.library._index._data", None)
    videos, audio = tmp_path / "v", tmp_path / "a"
    videos.mkdir()
    audio.mkdir()
    library.invalidate_cache()
    assert library.all_entries(videos, audio) == []
    assert index.with_name("library.json.bad").exists()


def test_corrupt_playlists_start_empty(temp_playlists):
    temp_playlists.write_text(GARBAGE, encoding="utf-8")
    assert playlist.list_playlists() == []
    assert temp_playlists.with_name("playlists.json.bad").exists()
