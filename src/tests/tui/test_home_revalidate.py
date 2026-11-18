"""Stale-while-revalidate for Home: show the cache at once, read behind it, announce what is new."""

import json
import time

import pytest

from src import cache as cache_mod


def _entries(n, prefix):
    return [{"id": f"{prefix}{i:06d}"[:11], "title": f"{prefix}{i}"} for i in range(n)]


class _Cursor:
    def __init__(self, rows):
        self.rows, self.takes, self.ids, self.exhausted, self.closed = rows, 0, [], False, False

    def take(self, count, skip_ids, **_):
        self.takes += 1
        self.ids = [e["id"] for e in self.rows]
        return [dict(e) for e in self.rows]

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a: None)


def _seed_cache(app, age_s):
    cached = _entries(30, "old")
    for e in cached:
        app.cache.put_video(e)
    app.cache.put_feed("home", [e["id"] for e in cached])
    path = cache_mod.CACHE_DIR / "feed_home.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_cached_at"] = time.time() - age_s
    path.write_text(json.dumps(data), encoding="utf-8")
    return cached


def _install(monkeypatch, cursor):
    monkeypatch.setattr("src.feed_cursor.FeedCursor", lambda *a, **k: cursor)


async def test_a_stale_cache_shows_at_once_and_announces_new_items(app, monkeypatch):
    _seed_cache(app, 700)
    cursor = _Cursor(_entries(5, "new") + _entries(10, "old"))
    _install(monkeypatch, cursor)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.6)
        panel = app.screen._list()
        assert cursor.takes == 1
        assert "↑ 5 new · r to refresh" in panel._status_note()
        ids = panel.seen_ids
        assert not any(i.startswith("new") for i in ids) and any(i.startswith("old") for i in ids)


async def test_the_cursor_row_does_not_move_when_new_items_arrive(app, monkeypatch):
    _seed_cache(app, 700)
    cursor = _Cursor(_entries(5, "new"))
    _install(monkeypatch, cursor)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.6)
        panel = app.screen._list()
        before = panel.selected_entry["id"], panel.current_page, panel.loaded_count
        await pilot.pause(0.3)
        assert (panel.selected_entry["id"], panel.current_page, panel.loaded_count) == before


async def test_a_young_cache_is_not_revalidated(app, monkeypatch):
    _seed_cache(app, 60)
    cursor = _Cursor(_entries(5, "new"))
    _install(monkeypatch, cursor)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.6)
        assert cursor.takes == 0
        assert "new" not in app.screen._list()._status_note()


async def test_a_failed_revalidation_is_silent(app, monkeypatch):
    _seed_cache(app, 700)
    cursor = _Cursor([])

    def boom(*a, **k):
        raise RuntimeError("down")

    cursor.take = boom
    _install(monkeypatch, cursor)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.6)
        assert app.screen._list().loaded_count >= 20


def test_revalidate_threshold_setting_is_validated(tmp_path):
    from src.config import Config

    cfg = Config(path=str(tmp_path / "c.yaml"))
    assert cfg.cache_ttl("home_revalidate") == 600
    cfg._data["cache_ttl"]["home_revalidate"] = "soon"
    assert cfg.cache_ttl("home_revalidate") == 600
    cfg._data["cache_ttl"]["home_revalidate"] = 30
    assert cfg.cache_ttl("home_revalidate") == 30
