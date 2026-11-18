"""List tools on the shared list: day headers, filter f, marks m/M, remove D, undo u (History is the first user)."""

import time
from unittest.mock import patch

import pytest

from src import history
from src.tui.screens.channel_screen import ChannelScreen
from src.tui.widgets.video_list import HeaderListItem, VideoListItem, VideoListPanel

DAY = 86400.0


@pytest.fixture(autouse=True)
def no_detail_network(monkeypatch):
    """Focusing a row would fetch metadata and a thumbnail; these tests are about the list."""
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)


@pytest.fixture
def seeded(temp_history, monkeypatch):
    """45 history rows, one every 5 hours (about 9 days), titles `Clip i even|odd`; i = 0 is the newest."""
    base = time.time()
    for i in reversed(range(45)):
        with monkeypatch.context() as m:
            m.setattr("src.history.time.time", lambda t=base - i * 5 * 3600: t)
            history.add({"id": f"id{i:03d}", "title": f"Clip {i} {'odd' if i % 2 else 'even'}", "uploader": "Chan"})
    return [e["id"] for e in history.all_entries()]


def panel_of(app) -> VideoListPanel:
    return app.screen.query_one("#video-list-panel", VideoListPanel)


def children(panel):
    return list(panel._lv.children)


def rows(panel):
    return [c for c in children(panel) if isinstance(c, VideoListItem)]


def cursor_id(panel):
    entry = panel.selected_entry
    return entry["id"] if entry else None


async def open_history(app, pilot):
    await pilot.pause(0.8)  # a running home load is not cancelled by a tab switch and would add rows here
    await pilot.press("f4")
    await pilot.pause(0.6)


async def type_text(pilot, text):
    for ch in text:
        await pilot.press("space" if ch == " " else ch)
    await pilot.pause(0.2)


async def test_history_shows_day_headers_that_the_cursor_skips(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        kids = children(panel)
        assert isinstance(kids[0], HeaderListItem) and kids[0]._label == "Today"
        labels = [c._label for c in kids if isinstance(c, HeaderListItem)]
        assert "Yesterday" in labels and len(rows(panel)) == 20
        assert cursor_id(panel) == seeded[0]
        for _ in range(19):
            await pilot.press("j")
            await pilot.pause(0.02)
            assert isinstance(panel._lv.highlighted_child, VideoListItem)
        assert cursor_id(panel) == seeded[19]
        await pilot.press("g")
        await pilot.pause(0.1)
        assert cursor_id(panel) == seeded[0]
        await pilot.press("G")
        await pilot.pause(0.2)
        assert panel.current_page == 3 and cursor_id(panel) == seeded[-1]
        assert panel._page_indicator._note == "45 videos"


async def test_paging_and_play_keys_still_work_with_headers(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("l")
        await pilot.pause(0.2)
        assert panel.current_page == 2 and cursor_id(panel) == seeded[20]
        await pilot.press("h")
        await pilot.pause(0.2)
        assert panel.current_page == 1
        with patch.object(app.screen, "_watch") as watch:
            await pilot.press("v")
            await pilot.pause(0.1)
        assert watch.call_args.args[0]["id"] == seeded[0]


async def test_filter_works_on_every_page_and_esc_restores_order_and_cursor(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("f")
        await type_text(pilot, "even")
        assert panel.filter_active and panel._filter_bar.has_focus
        assert panel.current_page == 1 and panel.total_pages == 2
        assert not any(isinstance(c, HeaderListItem) for c in children(panel))
        assert all("even" in r.entry["title"] for r in rows(panel))
        assert "23 of 45 match" in panel._page_indicator._note
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert not panel.filter_active and not panel._filter_bar.display
        assert panel.total_pages == 3 and [r.entry["id"] for r in rows(panel)] == seeded[:20]


async def test_clearing_the_filter_keeps_the_cursor_on_the_same_video(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("f")
        await type_text(pilot, "Clip 40")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert cursor_id(panel) == "id040" and panel._lv.has_focus
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert not panel.filter_active
        assert panel.current_page == 3 and cursor_id(panel) == "id040"


async def test_enter_keeps_the_filter_and_hands_keys_back_to_the_list(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("f")
        await type_text(pilot, "odd")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert panel.filter_active and panel._lv.has_focus and panel._filter_bar.display
        first = cursor_id(panel)
        await pilot.press("j")
        await pilot.pause(0.1)
        assert cursor_id(panel) != first and panel._filter_bar.value == "odd"
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert not panel.filter_active and len(rows(panel)) == 20


async def test_typing_movement_letters_in_the_filter_does_not_move_the_list(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("f")
        await type_text(pilot, "jkhlgq")
        assert panel._filter_bar.value == "jkhlgq" and panel.current_page == 1
        assert app.is_running


async def test_filter_with_no_match_shows_nothing_and_extension_is_off(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("f")
        await type_text(pilot, "zzzz")
        assert rows(panel) == [] and panel._page_indicator._note == "0 of 45 match"
        assert app.screen._can_extend() is False


async def test_marks_toggle_move_down_and_survive_paging(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("m", "m")
        await pilot.pause(0.1)
        assert cursor_id(panel) == seeded[2] and [r.marked for r in rows(panel)[:3]] == [True, True, False]
        assert "●" in rows(panel)[0]._cached_markup
        await pilot.press("l")
        await pilot.pause(0.2)
        await pilot.press("h")
        await pilot.pause(0.2)
        assert [r.marked for r in rows(panel)[:2]] == [True, True]
        assert "2 marked" in panel._page_indicator._note
        await pilot.press("M")
        await pilot.pause(0.1)
        assert all(r.marked for r in rows(panel))
        await pilot.press("M")
        await pilot.pause(0.1)
        assert not any(r.marked for r in rows(panel))


async def test_marks_clear_on_view_change(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        await pilot.press("m")
        await pilot.press("f1")
        await pilot.pause(0.3)
        await pilot.press("f4")
        await pilot.pause(0.6)
        assert not any(r.marked for r in rows(panel_of(app)))


async def test_delete_asks_once_then_removes_and_repages(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        bar = app.screen._detail().action_bar
        await pilot.press("D")
        await pilot.pause(0.1)
        assert bar._prompt and 'Remove "Clip 0 even"?' in bar._prompt
        await pilot.press("y")
        await pilot.pause(0.3)
        assert bar._prompt is None
        assert [e["id"] for e in history.all_entries()] == seeded[1:]
        assert cursor_id(panel) == seeded[1] and len(rows(panel)) == 20
        assert panel._page_indicator._note == "44 videos"


@pytest.mark.parametrize("key", ["n", "escape", "j", "enter", "q"])
async def test_any_other_key_cancels_the_removal_and_does_nothing_else(app, seeded, key):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("D")
        await pilot.press(key)
        await pilot.pause(0.2)
        assert app.is_running and app.screen._pending_remove is None
        assert len(history.all_entries()) == 45 and cursor_id(panel) == seeded[0]


async def test_delete_removes_all_marked_rows_across_pages(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("m", "m")
        await pilot.press("l")
        await pilot.pause(0.2)
        await pilot.press("m")
        await pilot.press("D")
        await pilot.pause(0.1)
        assert "Remove 3 items?" in app.screen._detail().action_bar._prompt
        await pilot.press("y")
        await pilot.pause(0.3)
        assert len(history.all_entries()) == 42
        assert not {seeded[0], seeded[1], seeded[20]} & {e["id"] for e in history.all_entries()}
        assert panel._marked == set()


async def test_delete_inside_a_filter_keeps_the_filter(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("f")
        await type_text(pilot, "even")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.press("D", "y")
        await pilot.pause(0.3)
        assert panel.filter_active and "22 of 44 match" in panel._page_indicator._note


async def test_undo_restores_at_the_original_position_and_says_what(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        await pilot.press("j", "j", "D", "y")
        await pilot.pause(0.3)
        assert seeded[2] not in {e["id"] for e in history.all_entries()}
        with patch.object(app.screen, "notify") as notify:
            await pilot.press("u")
            await pilot.pause(0.3)
        assert [e["id"] for e in history.all_entries()] == seeded
        assert cursor_id(panel) == seeded[2]
        assert "Restored 1 video to History" in notify.call_args.args[0]
        await pilot.press("u")
        await pilot.pause(0.1)
        assert app.screen._undo is None


async def test_undo_expires_after_thirty_seconds(app, seeded):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        await pilot.press("D", "y")
        await pilot.pause(0.2)
        tab, records, _ = app.screen._undo
        app.screen._undo = (tab, records, time.monotonic() - 31)
        await pilot.press("u")
        await pilot.pause(0.1)
        assert len(history.all_entries()) == 44


async def test_removing_the_last_row_empties_the_list(app, temp_history):
    history.add({"id": "only", "title": "Only"})
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        await pilot.press("D", "y")
        await pilot.pause(0.3)
        assert history.all_entries() == [] and rows(panel_of(app)) == []
        await pilot.press("u")
        await pilot.pause(0.3)
        assert len(rows(panel_of(app))) == 1


@pytest.mark.parametrize("tab,key,said", [("home", "f1", "Home rows cannot be removed")])
async def test_tabs_without_a_remove_handler_say_why(app, temp_history, tab, key, said):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.press(key)
        await pilot.pause(0.5)
        with patch.object(app.screen, "notify") as notify:
            await pilot.press("D")
            await pilot.pause(0.1)
        assert said in notify.call_args.args[0]
        assert app.screen._pending_remove is None


async def test_filter_on_an_empty_list_says_so(app, temp_history):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        with patch.object(app.screen, "notify") as notify:
            await pilot.press("f")
            await pilot.pause(0.1)
        assert "Nothing to filter" in notify.call_args.args[0]


async def test_channel_page_gets_the_filter_but_not_the_list_tools(app, temp_history):
    async with app.run_test(size=(110, 40)) as pilot:
        with patch.object(ChannelScreen, "_load_channel_info"), patch.object(ChannelScreen, "_start_content_once"):
            app.push_screen(ChannelScreen("https://www.youtube.com/channel/UCx", "Chan"))
            await pilot.pause(0.3)
        panel = app.screen.query_one("#ch-video-list", VideoListPanel)
        panel.add_entries(1, [{"id": f"c{i}", "title": f"Upload {i}"} for i in range(30)])
        panel.load_page(1)
        panel.finish_loading()
        await pilot.pause(0.2)
        await pilot.press("f")
        await type_text(pilot, "upload 2")
        assert panel.filter_active and all("2" in r.entry["title"] for r in rows(panel))
        assert not hasattr(app.screen, "action_delete")
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ChannelScreen) and not panel.filter_active
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, ChannelScreen)


async def test_rows_per_page_sets_the_page_size_at_the_next_list_load(app, seeded):
    app.config.set("rows_per_page", 10)
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        assert panel.page_size == 10 and len(rows(panel)) == 10 and panel.total_pages == 5
        app.config.set("rows_per_page", 50)
        assert panel.page_size == 10
        await pilot.press("f1")
        await pilot.pause(0.3)
        await pilot.press("f4")
        await pilot.pause(0.6)
        assert panel.page_size == 50 and panel.total_pages == 1


@pytest.fixture
def watched_unevenly(temp_history):
    for vid in ("aaa", "bbb", "ccc"):  # newest last added is first in the list: ccc, bbb, aaa
        history.add({"id": vid, "title": f"Clip {vid}", "uploader": "Chan", "duration": 600})
    history.add({"id": "aaa", "title": "Clip aaa", "uploader": "Chan", "duration": 600})  # aaa: 2 plays, now newest
    history.record_progress("bbb", resume_s=125, watched=900)
    history.record_progress("ccc", resume_s=None, watched=60)
    return ["aaa", "ccc", "bbb"]


async def test_s_on_local_history_sorts_by_plays_and_time_and_drops_day_headers(app, watched_unevenly):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        panel = panel_of(app)
        assert [r.entry["id"] for r in rows(panel)] == ["aaa", "ccc", "bbb"]
        assert any(isinstance(c, HeaderListItem) for c in children(panel))
        await pilot.press("s")
        await pilot.pause(0.2)
        await pilot.press("l")  # longest watched
        await pilot.pause(0.6)
        assert [r.entry["id"] for r in rows(panel)] == ["bbb", "ccc", "aaa"]
        assert not any(isinstance(c, HeaderListItem) for c in children(panel))
        await pilot.press("s")
        await pilot.pause(0.2)
        await pilot.press("m")  # most watched: aaa has two plays, the tie goes to more time watched
        await pilot.pause(0.6)
        assert [r.entry["id"] for r in rows(panel)] == ["aaa", "bbb", "ccc"]
        await pilot.press("s")
        await pilot.pause(0.2)
        await pilot.press("r")
        await pilot.pause(0.6)
        assert any(isinstance(c, HeaderListItem) for c in children(panel))


async def test_history_rows_show_the_resume_point_and_play_count(app, watched_unevenly):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_history(app, pilot)
        by_id = {r.entry["id"]: r._cached_markup for r in rows(panel_of(app))}
        assert "▶ 2:05 / 10:00" in by_id["bbb"] and "▶" not in by_id["ccc"] and "×2" in by_id["aaa"]


async def test_s_outside_search_and_local_history_is_still_a_hint(app, monkeypatch):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.8)
        shown = []
        monkeypatch.setattr(app.screen, "notify", lambda msg, **kw: shown.append(msg))
        await pilot.press("s")
        await pilot.pause(0.1)
        assert shown and "search results" in shown[0] and "local History" in shown[0]
