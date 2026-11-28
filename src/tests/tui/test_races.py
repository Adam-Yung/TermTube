"""Races and cancellation, deterministic: fakes block on ``threading.Event`` gates, the test releases them."""

import asyncio
import threading
from functools import partial
from unittest.mock import MagicMock

import pytest

from src.feed_cursor import FeedCursor
from src.tests.fakes import silence_detail_workers, silence_empty_feed_modal
from src.tests.tui.waits import settle, until
from src.tui.messages import PlayerStateUpdated
from src.tui.widgets.video_list import VideoListPanel

WAIT = 10  # a bound for a gate that never opens, never a delay the tests rely on


def rows(prefix, n=3):
    return [
        {"id": f"{prefix}-{i}".ljust(11, "_"), "title": f"{prefix} {i}", "uploader": "C", "duration": 60}
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def quiet(monkeypatch, temp_history, temp_playlists):
    silence_detail_workers(monkeypatch)
    silence_empty_feed_modal(monkeypatch)


class Gate:
    """A fake fetch that reports it started, then waits for the test to let it finish."""

    def __init__(self, result):
        self.started, self.release, self.result = threading.Event(), threading.Event(), result
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        self.started.set()
        assert self.release.wait(WAIT)
        return self.result


def _local_rows(prefix, path):
    return [dict(e, _local_path=path) for e in rows(prefix)]


def _same(value):
    return value


class _Sequence:
    """A fake fetch answered by ``initial`` on its first call and by ``later`` after it."""

    def __init__(self, initial, later):
        self.initial, self.later, self.calls = initial, later, 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.initial() if self.calls == 1 else self.later()


def shown_ids(screen):
    return [e["id"] for e in screen.query_one(VideoListPanel).visited_entries()]


async def test_a_tab_switch_during_a_load_drops_the_old_result(app, monkeypatch):
    home = Gate(rows("home"))
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", home)
    local = [dict(e, _local_path="/x/a.mp4") for e in rows("lib")]
    monkeypatch.setattr("src.library.all_entries", lambda *a, **k: local)
    async with app.run_test(size=(100, 30)) as pilot:
        await until(pilot, home.started.is_set)
        screen = app.screen
        screen._load_view("library")
        await settle(app, pilot)
        home.release.set()
        await settle(app, pilot)
        assert shown_ids(screen) == [e["id"] for e in rows("lib")] and screen._active_workers == 0


def _gated_only_for_cats(first, query, *a, **k):
    return first(query) if query == "cats" else rows("new")


async def test_a_search_during_a_load_shows_only_the_newest_query(app, monkeypatch):
    first = Gate(rows("old"))

    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    monkeypatch.setattr("src.ytdlp.fetch_search_batch", partial(_gated_only_for_cats, first))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        screen = app.screen
        screen._search.push("cats")
        screen._load_view("search")
        await until(pilot, first.started.is_set)
        screen._search.push("dogs")
        screen._load_view("search")
        await settle(app, pilot)
        first.release.set()
        await settle(app, pilot)
        assert shown_ids(screen) == [e["id"] for e in rows("new")] and screen._active_workers == 0


async def test_rapid_rail_changes_end_on_the_last_selection(app, monkeypatch):
    slow = Gate([dict(e, _local_path="/x/a.mp4") for e in rows("all")])
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    monkeypatch.setattr("src.library.all_entries", _Sequence(slow, partial(_local_rows, "fast", "/x/b.mp4")))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        screen = app.screen
        screen._load_view("library")
        await until(pilot, slow.started.is_set)
        for view in ("library:video", "library:audio", "library"):
            screen._load_view(view)
        await settle(app, pilot)
        slow.release.set()
        await settle(app, pilot)
        assert shown_ids(screen) == [e["id"] for e in rows("fast")] and screen._active_workers == 0


def _outlive_the_app(started, release, done, holder, raised, *a, **k):
    """A fetch still running at quit: its late UI hand-off must be dropped, not raise on the closed loop."""
    started.set()
    assert release.wait(WAIT)
    try:
        holder[0]._ui(lambda: None)
    except Exception as exc:
        raised.append(exc)
    done.set()
    return []


async def test_quitting_during_a_load_leaves_the_worker_quiet(app, monkeypatch):
    started, release, done = (threading.Event() for _ in range(3))
    raised, holder = [], []

    monkeypatch.setattr("src.ytdlp.fetch_page_batch",
                        partial(_outlive_the_app, started, release, done, holder, raised))
    async with app.run_test(size=(100, 30)) as pilot:
        await until(pilot, started.is_set)
        holder.append(app.screen)
        app.screen.action_quit_app()
        await pilot.pause()
    assert not app.is_running
    release.set()
    assert await asyncio.to_thread(done.wait, WAIT)
    assert not raised


async def test_a_removal_question_is_dropped_when_the_list_is_replaced(app, monkeypatch):
    from src import history

    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    async with app.run_test(size=(100, 30)) as pilot:
        for e in rows("h"):
            history.add(e, app.config)
        screen = app.screen
        screen._current_tab = "history"
        screen._load_view("history")
        await settle(app, pilot)
        screen.action_delete()
        assert screen._pending_remove is not None
        screen._load_view("history")
        await settle(app, pilot)
        assert screen._pending_remove is None
        await pilot.press("y")
        await pilot.pause()
        assert len(history.all_entries()) == 3


class _SlowYdl:
    """An extractor whose second row arrives only after ``release``; counts how often it is closed."""

    def __init__(self, started, release, exits):
        self.started, self.release, self.exits = started, release, exits

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.exits.append(1)

    def extract_info(self, url, download=False):
        return {"entries": self._rows()}

    def _rows(self):
        yield {"id": "AAAAAAAAAAA", "title": "a", "duration": 60, "url": "u"}
        self.started.set()
        assert self.release.wait(WAIT)
        yield {"id": "BBBBBBBBBBB", "title": "b", "duration": 60, "url": "u"}


async def test_closing_a_feed_cursor_while_a_take_runs_ends_the_take_and_closes_the_extractor_once(monkeypatch):
    started, release = threading.Event(), threading.Event()
    exits = []
    monkeypatch.setattr("src.ytdlp._make_ydl", lambda *a, **k: _SlowYdl(started, release, exits))
    cursor = FeedCursor("https://example.invalid/feed", MagicMock(), MagicMock())
    result = []
    thread = threading.Thread(target=lambda: result.extend(cursor.take(5, set())))
    thread.start()
    assert await asyncio.to_thread(started.wait, WAIT)
    cursor.close()
    release.set()
    await asyncio.to_thread(thread.join, WAIT)
    assert not thread.is_alive() and [e["id"] for e in result] == ["AAAAAAAAAAA"] and exits == [1]
    cursor.close()
    assert exits == [1] and cursor.take(5, set()) == []


async def test_a_channel_screen_popped_while_its_workers_run_drops_their_results(app, monkeypatch):
    from src import innertube
    from src.tui.screens.channel_screen import ChannelScreen

    first, more = Gate(innertube.ChannelPage(rows("ch", 30), "T1")), Gate(innertube.ChannelPage(rows("mo"), ""))
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    monkeypatch.setattr(
        "src.innertube.fetch_channel_page", lambda cid, kind, token="", **k: more() if token else first()
    )
    async with app.run_test(size=(110, 34)) as pilot:
        await settle(app, pilot)
        app.push_screen(ChannelScreen("https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw", "Rick"))
        await until(pilot, first.started.is_set)
        screen = app.screen
        app.pop_screen()
        await pilot.pause()
        first.release.set()
        await settle(app, pilot)
        # an extension fetch that was already running when the screen went must end quietly too
        screen._extend_content("videos", "T1", True, screen._content_session)
        await until(pilot, more.started.is_set)
        more.release.set()
        await settle(app, pilot)
        assert app.is_running and app.screen is not screen


async def test_a_filter_typed_while_an_extension_lands_keeps_the_filtered_view(app, monkeypatch):
    first = [dict(e, title=f"cat {e['title']}") for e in rows("a", 30)]
    gate = Gate(rows("b", 30))
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", _Sequence(partial(_same, first), gate))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        panel = app.screen.query_one(VideoListPanel)
        app.screen._request_extension(show=False)
        panel._apply_filter("cat")
        gate.release.set()
        await settle(app, pilot)
        held = [e for page in panel._filtered_pages.values() for e in page]
        assert panel.filter_active and held and all("cat" in e["title"] for e in held)
        panel._apply_filter("")
        assert not panel.filter_active


async def test_undo_after_the_list_changed_view_restores_the_data_not_the_wrong_list(app, monkeypatch):
    from src import history

    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: rows("home"))
    async with app.run_test(size=(100, 30)) as pilot:
        for e in rows("h"):
            history.add(e, app.config)
        await settle(app, pilot)
        screen = app.screen
        screen._current_tab = "history"
        screen._load_view("history")
        await settle(app, pilot)
        screen._remove([rows("h")[0]], "")
        assert len(history.all_entries()) == 2
        screen._current_tab = "home"
        screen._load_view("home")
        await settle(app, pilot)
        before = shown_ids(screen)
        screen.action_undo()
        await settle(app, pilot)
        assert len(history.all_entries()) == 3 and shown_ids(screen) == before


async def test_marks_survive_a_re_page(app, monkeypatch):
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: rows("m", 45))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        panel = app.screen.query_one(VideoListPanel)
        panel.mark_page()
        marked = {e["id"] for e in panel.marked_entries()}
        assert marked
        panel.load_page(2)
        panel.load_page(1)
        panel.set_matcher(None)
        panel._apply_filter("m")
        panel._apply_filter("")
        assert {e["id"] for e in panel.marked_entries()} == marked


def _gated_history(slow, *a, **k):
    return slow() if "history" in str(k.get("feed_key")) else []


async def test_a_history_source_switch_during_a_load_shows_the_last_source(app, monkeypatch):
    slow = Gate(rows("yt"))
    monkeypatch.setattr("src.tui.screens.mixins.feed_loader.resolve_browser", lambda cfg: "chrome")
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", partial(_gated_history, slow))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        screen = app.screen
        screen._current_tab = "history"
        screen._load_view("history")
        await settle(app, pilot)
        screen._select_collection("history:yt")  # blocks in the gate
        await until(pilot, slow.started.is_set)
        screen._select_collection("history:wl")
        screen._select_collection("history")  # back to local
        await settle(app, pilot)
        slow.release.set()
        await settle(app, pilot)
        assert screen._current_tab == "history" and not any(i.startswith("yt") for i in shown_ids(screen))
        assert screen._active_workers == 0


async def test_the_queue_page_follows_a_queue_that_empties_and_a_track_that_changes(app, monkeypatch):
    from src.tui.audio_controller import AudioController
    from src.tui.screens.queue_screen import QueueScreen

    monkeypatch.setattr(AudioController, "_launch_worker", lambda *a, **k: None)
    monkeypatch.setattr("src.tui.audio_controller.cleanup_ipc", lambda path: None)
    a, b, c, d = rows("a", 1)[0], rows("b", 1)[0], rows("c", 1)[0], rows("d", 1)[0]
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        controller = app.audio
        controller._play_pending, controller._entry, controller._queue = True, a, [b, c, d]
        app.push_screen(QueueScreen())
        await pilot.pause()
        page = app.screen
        await until(pilot, lambda: page._selected_entry() is a)  # rows mount late on a loaded machine
        await pilot.press("down", "down", "down")
        await until(pilot, lambda: page._selected_entry() is d)
        controller.remove_queued(2)
        controller.remove_queued(1)
        controller.remove_queued(0)
        await pilot.pause()
        await pilot.pause(0.3)
        assert page._ids == [a["id"]]
        await pilot.press("J", "D", "enter")  # a move, a remove and a jump on the playing row only notify
        controller._play_pending, controller._entry = False, None
        controller._broadcast(lambda: PlayerStateUpdated(0, 0, False, playing=False))
        await pilot.pause()
        assert page._ids == [] and app.screen is page
        await pilot.press("D", "J", "enter", "u")
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not page
