"""Tests for src/history.py: local watch history."""

import json

import pytest

from src import history, store
from src.config import Config


@pytest.fixture
def cfg(tmp_path):
    return Config(path=str(tmp_path / "config.yaml"))


def _disk(path):
    store.flush_all()
    return json.loads(path.read_text(encoding="utf-8"))


class TestAdd:
    def test_stores_a_slim_record(self, temp_history):
        history.add({
            "id": "vid1", "title": "First", "uploader": "U", "channel_id": "UC1", "duration": 60,
            "thumbnail": "http://t/1.jpg", "description": "long " * 500, "formats": [{"url": "x"}],
            "_local_path": "/x/y.mp4", "_sidecar": {"a": 1},
        })
        (rec,) = history.all_entries()
        assert set(rec) == {
            "id", "title", "uploader", "channel_id", "duration", "thumbnail", "view_count", "upload_date",
            "watched_at", "plays", "seconds", "resume_s", "source",
        }
        assert rec["plays"] == 1 and rec["resume_s"] is None and rec["source"] == "local"

    def test_channel_stands_in_for_uploader(self, temp_history):
        history.add({"id": "v", "channel": "Chan"})
        assert history.all_entries()[0]["uploader"] == "Chan"

    def test_no_id_is_ignored(self, temp_history):
        history.add({"title": "No ID"})
        assert history.all_entries() == []

    def test_dedupes_by_id_counts_plays_and_keeps_resume(self, temp_history):
        history.add({"id": "vid1", "title": "First"})
        history.add({"id": "vid2", "title": "Second"})
        history._store.update(lambda d: d[0].update(seconds=30, resume_s=12.5) or True)
        history.add({"id": "vid2", "title": "Second Again"})
        entries = history.all_entries()
        assert [e["id"] for e in entries] == ["vid2", "vid1"]
        assert entries[0]["title"] == "Second Again"
        assert entries[0]["plays"] == 2
        assert entries[0]["seconds"] == 30 and entries[0]["resume_s"] == 12.5

    def test_newest_first(self, temp_history):
        for i in ("old", "mid", "new"):
            history.add({"id": i})
        assert [e["id"] for e in history.all_entries()] == ["new", "mid", "old"]


class TestSettings:
    def test_disabled_records_nothing(self, temp_history, cfg):
        cfg.set("history", False)
        history.add({"id": "v"}, cfg)
        assert history.all_entries() == []

    def test_cap_follows_history_max_clamped(self, temp_history, cfg):
        cfg.set("history_max", 1)
        assert cfg.history_max == 50
        for i in range(60):
            history.add({"id": f"v{i}"}, cfg)
        entries = history.all_entries()
        assert len(entries) == 50 and entries[0]["id"] == "v59"

    def test_config_accessors_validate(self, cfg):
        assert cfg.history_enabled is True and cfg.history_max == 500
        cfg.set("history_max", 99999)
        assert cfg.history_max == 5000
        cfg.set("history_max", "lots")
        assert cfg.history_max == 500
        cfg.set("history", "no")
        assert cfg.history_enabled is True


class TestRemoveAndClear:
    def test_remove_many_returns_copies_of_what_it_removed(self, temp_history):
        for vid in "abc":
            history.add({"id": vid, "title": vid.upper()})
        removed = history.remove_many(["a", "c", "zzz"])
        assert sorted(r["id"] for r in removed) == ["a", "c"]
        assert [e["id"] for e in history.all_entries()] == ["b"]
        assert removed[0] is not history.all_entries()[0]
        assert history.remove_many(["zzz"]) == []

    def test_restore_puts_records_back_by_watched_time(self, temp_history, monkeypatch):
        clock = iter([100.0, 200.0, 300.0])
        monkeypatch.setattr("src.history.time.time", lambda: next(clock))
        for vid in "abc":
            history.add({"id": vid})
        removed = history.remove_many(["b"])
        history.restore(removed)
        assert [e["id"] for e in history.all_entries()] == ["c", "b", "a"]

    def test_restore_keeps_the_newer_record_of_a_video_watched_since(self, temp_history):
        history.add({"id": "a"})
        removed = history.remove_many(["a"])
        history.add({"id": "a"})
        history.restore(removed)
        assert [e["id"] for e in history.all_entries()] == ["a"]

    def test_clear_writes_at_once(self, temp_history):
        history.add({"id": "a"})
        history.clear()
        assert history.all_entries() == []
        assert json.loads(temp_history.read_text(encoding="utf-8"))["data"] == []


class TestPersistence:
    def test_flushed_and_reloaded(self, temp_history):
        history.add({"id": "p1", "title": "A"})
        history.add({"id": "p2", "title": "B"})
        raw = _disk(temp_history)
        assert raw["version"] == 2
        assert [e["id"] for e in raw["data"]] == ["p2", "p1"]

    def test_in_memory_list_is_updated_before_the_write(self, temp_history):
        history.add({"id": "p1"})
        assert [e["id"] for e in history.all_entries()] == ["p1"]

    def test_migrates_the_v1_file_to_slim_records(self, temp_history):
        old = [{"id": "a", "title": "T", "uploader": "U", "description": "x" * 1000, "formats": [1],
                "_watched_at": 111.0, "view_count": 5}, {"title": "no id"}]
        temp_history.write_text(json.dumps(old), encoding="utf-8")
        (rec,) = history.all_entries()
        assert rec["watched_at"] == 111.0 and rec["plays"] == 1 and rec["view_count"] == 5
        assert "description" not in rec and "formats" not in rec and "_watched_at" not in rec
        assert _disk(temp_history)["version"] == 2

    def test_a_failed_write_does_not_raise_and_keeps_the_entry(self, temp_history, monkeypatch):
        def locked(*args):
            raise PermissionError("file is held open by another process")

        monkeypatch.setattr(store, "atomic_write", locked)
        history.add({"id": "AAAAAAAAAAA", "title": "t"})
        store.flush_all()
        assert [e["id"] for e in history.all_entries()] == ["AAAAAAAAAAA"]


def test_import_entries_adds_new_rows_after_dated_ones_and_keeps_existing(temp_history):
    history.add({"id": "dated000001", "title": "Mine", "uploader": "A"})
    added = history.import_entries(
        [
            {"id": "dated000001", "title": "Theirs"},
            {"id": "yt000000001", "title": "T", "uploader": "U", "duration": 90},
            {"title": "no id"},
        ]
    )
    assert added == 1
    rows = history.all_entries()
    assert [r["id"] for r in rows] == ["dated000001", "yt000000001"]
    assert rows[0]["title"] == "Mine" and rows[0]["source"] == "local"
    assert rows[1]["source"] == "yt" and rows[1]["watched_at"] is None and rows[1]["duration"] == 90
    assert history.import_entries([{"id": "yt000000001"}]) == 0


def test_a_new_watch_goes_before_imported_rows(temp_history):
    history.import_entries([{"id": "yt000000001", "title": "T"}])
    history.add({"id": "new00000001", "title": "N"})
    assert [r["id"] for r in history.all_entries()] == ["new00000001", "yt000000001"]
