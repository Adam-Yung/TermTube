"""Tests for src/playlist.py: v2 playlists, migration from v1, ordering, concurrency, pins."""

import json
import threading
from unittest.mock import MagicMock

from src import playlist


def vid(n, title=None):
    return {"id": f"vid{n}", "title": title or f"Video {n}", "uploader": "Chan", "duration": 60}


def ids(pid):
    return [i["id"] for i in playlist.get(pid)["items"]]


class TestCreateAndNames:
    def test_empty_initially(self, temp_playlists):
        assert playlist.list_playlists() == []

    def test_create_has_stable_id_and_slim_snapshots(self, temp_playlists):
        pl = playlist.create("Favorites", [{**vid(1), "formats": [{"x": 1}]}])
        assert pl["id"].startswith("pl_") and pl["kind"] == "manual"
        item = playlist.get(pl["id"])["items"][0]
        assert item["title"] == "Video 1" and item["added"] > 0 and "formats" not in item

    def test_names_are_unique_case_insensitive(self, temp_playlists):
        assert playlist.create("Mix") is not None
        assert playlist.create("mix") is None and playlist.create("  MIX ") is None
        assert playlist.create("   ") is None
        assert len(playlist.list_playlists()) == 1

    def test_rename_respects_uniqueness_and_allows_case_change(self, temp_playlists):
        a, b = playlist.create("A"), playlist.create("B")
        assert playlist.rename(b["id"], "a") is False
        assert playlist.rename(a["id"], "a") is True
        assert playlist.get(a["id"])["name"] == "a"
        assert playlist.rename("pl_nope", "X") is False and playlist.rename(a["id"], " ") is False

    def test_delete_returns_the_record_and_restore_puts_it_back(self, temp_playlists):
        pl = playlist.create("Gone", [vid(1)])
        record = playlist.delete(pl["id"])
        assert playlist.get(pl["id"]) is None and playlist.delete(pl["id"]) is None
        assert playlist.restore(record) is True and playlist.restore(record) is False
        assert ids(pl["id"]) == ["vid1"]


class TestItems:
    def test_add_skips_duplicates_and_reports_count(self, temp_playlists):
        pid = playlist.create("P")["id"]
        assert playlist.add_items(pid, [vid(1), vid(2), vid(1)]) == 2
        assert playlist.add_items(pid, [vid(2)]) == 0
        assert ids(pid) == ["vid1", "vid2"] and playlist.add_items("pl_nope", [vid(1)]) == 0

    def test_adding_a_known_video_fills_the_snapshot(self, temp_playlists):
        pid = playlist.create("P", [{"id": "vid1"}])["id"]
        playlist.add_items(pid, [vid(1, "Real title")])
        assert playlist.get(pid)["items"][0]["title"] == "Real title"

    def test_remove_and_restore_keep_positions(self, temp_playlists):
        pid = playlist.create("P", [vid(n) for n in range(5)])["id"]
        removed = playlist.remove_items(pid, ["vid1", "vid3", "missing"])
        assert [r["_pos"] for r in removed] == [1, 3] and ids(pid) == ["vid0", "vid2", "vid4"]
        assert playlist.restore_items(pid, removed) == 2
        assert ids(pid) == [f"vid{n}" for n in range(5)]
        assert all("_pos" not in i for i in playlist.get(pid)["items"])

    def test_move_item_bounds(self, temp_playlists):
        pid = playlist.create("P", [vid(n) for n in range(3)])["id"]
        assert playlist.move_item(pid, "vid0", 2) is True and ids(pid) == ["vid1", "vid2", "vid0"]
        assert playlist.move_item(pid, "vid0", 3) is False and playlist.move_item(pid, "vid0", -1) is False
        assert playlist.move_item(pid, "vid0", 2) is False and playlist.move_item(pid, "nope", 0) is False
        assert ids(pid) == ["vid1", "vid2", "vid0"]

    def test_transfer_copy_and_move(self, temp_playlists):
        a = playlist.create("A", [vid(1), vid(2)])["id"]
        b = playlist.create("B", [vid(2)])["id"]
        assert playlist.transfer(a, b, ["vid1", "vid2"]) == 1
        assert ids(a) == ["vid1", "vid2"] and ids(b) == ["vid2", "vid1"]
        assert playlist.transfer(a, b, ["vid1"], move=True) == 1
        assert ids(a) == ["vid2"] and playlist.transfer(a, a, ["vid2"]) == 0

    def test_membership_and_all_ids(self, temp_playlists):
        playlist.create("A", [vid(1), vid(2)])
        playlist.create("B", [vid(2)])
        assert playlist.video_playlists("vid2") == ["A", "B"] and playlist.video_playlists("zzz") == []
        assert playlist.all_video_ids() == {"vid1", "vid2"}

    def test_refresh_items_only_fills_empty_fields(self, temp_playlists):
        pid = playlist.create("P", [{"id": "vid1", "title": "Kept"}, {"id": "vid2"}])["id"]
        playlist.refresh_items([vid(1, "Other"), vid(2, "Filled")])
        titles = [i["title"] for i in playlist.get(pid)["items"]]
        assert titles == ["Kept", "Filled"]

    def test_reads_are_copies(self, temp_playlists):
        pid = playlist.create("P", [vid(1)])["id"]
        playlist.get(pid)["items"].clear()
        assert ids(pid) == ["vid1"]


class TestMigration:
    def write(self, path, raw):
        path.write_text(json.dumps(raw), encoding="utf-8")

    def test_v1_plain_and_enveloped_become_v2_with_backup(self, temp_playlists):
        self.write(temp_playlists, {"Mix": ["a", "b", "a"], "Other": ["c"]})
        pls = playlist.list_playlists()
        assert [p["name"] for p in pls] == ["Mix", "Other"]
        assert [i["id"] for i in pls[0]["items"]] == ["a", "b"] and pls[0]["items"][0]["title"] == ""
        backup = temp_playlists.with_name("playlists.json.v1")
        assert json.loads(backup.read_text(encoding="utf-8")) == {"Mix": ["a", "b", "a"], "Other": ["c"]}
        playlist._store.flush()
        assert json.loads(temp_playlists.read_text(encoding="utf-8"))["version"] == 2

    def test_existing_backup_is_not_overwritten(self, temp_playlists):
        backup = temp_playlists.with_name("playlists.json.v1")
        backup.write_text("precious", encoding="utf-8")
        self.write(temp_playlists, {"Mix": ["a"]})
        playlist.list_playlists()
        assert backup.read_text(encoding="utf-8") == "precious"

    def test_odd_v1_shapes_do_not_crash(self, temp_playlists):
        self.write(temp_playlists, {"Good": ["a", 3, None, ""], "Bad": "text", "  ": ["x"], "Nul": None})
        pls = {p["name"]: p for p in playlist.list_playlists()}
        assert [i["id"] for i in pls["Good"]["items"]] == ["a"] and pls["Bad"]["items"] == [] and "  " not in pls

    def test_list_instead_of_dict_gives_empty_playlists(self, temp_playlists):
        self.write(temp_playlists, ["a", "b"])
        assert playlist.list_playlists() == []

    def test_corrupt_file_is_kept_aside(self, temp_playlists):
        temp_playlists.write_text("{not json", encoding="utf-8")
        assert playlist.list_playlists() == []
        assert temp_playlists.with_name("playlists.json.bad").exists()

    def test_duplicate_names_differing_in_case_are_kept_apart(self, temp_playlists):
        self.write(temp_playlists, {"Mix": ["a"], "mix": ["b"], "MIX": ["c"]})
        pls = playlist.list_playlists()
        assert len({p["name"].casefold() for p in pls}) == 3 == len(pls)
        assert [p["items"][0]["id"] for p in pls] == ["a", "b", "c"]


def test_concurrent_adds_lose_no_update(temp_playlists):
    pid = playlist.create("Busy")["id"]

    def worker(n):
        for i in range(20):
            playlist.add_items(pid, [{"id": f"v{n}-{i}", "title": "t"}])

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(ids(pid)) == 120


def test_concurrent_creates_of_one_name_make_one(temp_playlists):
    results = []
    threads = [threading.Thread(target=lambda: results.append(playlist.create("Same"))) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(r is not None for r in results) == 1 and len(playlist.list_playlists()) == 1


class TestSyncPins:
    def test_pins_members_and_unpins_the_rest(self, temp_playlists):
        cache = MagicMock()
        playlist.create("P", [vid(1)])
        playlist.sync_pins(cache, ["vid1", "vid2"], [vid(1)])
        cache.pin_video.assert_called_once_with("vid1", vid(1))
        cache.pin_thumb.assert_called_once_with("vid1")
        cache.unpin_video.assert_called_once_with("vid2")

    def test_a_video_in_another_playlist_stays_pinned_after_removal(self, temp_playlists):
        cache = MagicMock()
        a = playlist.create("A", [vid(1)])["id"]
        playlist.create("B", [vid(1)])
        playlist.remove_items(a, ["vid1"])
        playlist.sync_pins(cache, ["vid1"])
        assert cache.unpin_video.call_count == 0 and cache.pin_video.call_count == 1
