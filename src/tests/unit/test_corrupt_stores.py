"""A damaged user file starts empty, leaves a `.bad` copy and never crashes the caller."""

import json

import pytest

from src import channel_bookmarks, history, library, playlist, search_history

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


STORES = [
    (history, "HISTORY_PATH", "_store"),
    (playlist, "_PLAYLISTS_PATH", "_store"),
    (search_history, "SEARCH_HISTORY_PATH", "_store"),
    (channel_bookmarks, "CHANNELS_PATH", "_store"),
    (library, "INDEX_PATH", "_index"),
]
DAMAGE = {
    "truncated": lambda: '{"version": 1, "data": [{"id": "a',
    "wrong type": lambda: json.dumps({"version": 1, "data": "text"}),
    "future version": lambda: json.dumps({"version": 999, "data": {}}),
    "bare scalar": lambda: "42",
}


@pytest.mark.parametrize("damage", DAMAGE)
@pytest.mark.parametrize("module, path_attr, store_attr", STORES, ids=lambda v: getattr(v, "__name__", str(v)))
def test_every_store_survives_a_damaged_file(tmp_path, monkeypatch, module, path_attr, store_attr, damage):
    path = tmp_path / "damaged.json"
    path.write_text(DAMAGE[damage](), encoding="utf-8")
    monkeypatch.setattr(module, path_attr, path)
    store = getattr(module, store_attr)
    default = store._default()
    assert store.read(lambda data: data == default)
    assert path.with_name("damaged.json.bad").exists() or path.with_name("damaged.json.v1").exists()
    store._data, store._loaded_from = None, None
