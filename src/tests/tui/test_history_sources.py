"""History tab sources: Local, and YouTube (read-only account list through the Home loader)."""

import pytest

from src import history
from src.tui.widgets.video_list import HeaderListItem, VideoListItem, VideoListPanel

ROWS = [
    {"id": "abcdefghij1", "title": "One", "uploader": "A", "duration": 61},
    {"id": "abcdefghij2", "title": "Two"},
    None,
    {"id": "bad"},
]


@pytest.fixture(autouse=True)
def quiet(monkeypatch, temp_history):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    # The startup Home load sees an empty patched feed and opens this modal; its mount races teardown on slow runners.
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a: None)


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.feed_loader.resolve_browser", lambda config: "firefox")


@pytest.fixture
def fetched(monkeypatch):
    calls = []

    def fake(url, config, cache, **kwargs):
        calls.append((url, kwargs))
        return [dict(r) for r in ROWS if r and len(r["id"]) == 11]

    monkeypatch.setattr("src.ytdlp.fetch_page_batch", fake)
    return calls


def yt_calls(calls):
    """Home loads at startup through the same function; only the History calls matter here."""
    return [c for c in calls if c[1]["feed_key"] == "yt_history"]


def items(panel):
    return [c for c in panel._lv.children if isinstance(c, VideoListItem)]


def panel_of(app) -> VideoListPanel:
    return app.screen.query_one("#video-list-panel", VideoListPanel)


async def test_y_cycles_local_and_youtube_and_the_tab_remembers_it(app, signed_in, fetched):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen.action_goto_tab("history")
        await pilot.pause(0.3)
        assert screen._current_tab == "history"
        await pilot.press("Y")
        await pilot.pause(0.5)
        assert screen._current_tab == "history:yt"
        screen.action_goto_tab("home")
        await pilot.pause(0.3)
        screen.action_goto_tab("history")
        await pilot.pause(0.3)
        assert screen._current_tab == "history:yt"
        await pilot.press("Y")
        await pilot.press("Y")
        await pilot.pause(0.3)
        assert screen._current_tab == "history"


async def test_youtube_rows_use_the_account_loader_and_carry_a_badge_and_no_day_headers(app, signed_in, fetched):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._current_tab = "history:yt"
        screen._load_view("history:yt")
        await pilot.pause(0.5)
        url, kwargs = yt_calls(fetched)[0]
        assert url == "https://www.youtube.com/feed/history"
        assert kwargs["auth"] is True and kwargs["feed_key"] == "yt_history"
        home = [c for c in fetched if c[1]["feed_key"] == "home"]
        assert home and home[0][1]["auth"] is True and home[0][0] == "https://www.youtube.com/"
        panel = panel_of(app)
        assert [i.entry["id"] for i in items(panel)] == ["abcdefghij1", "abcdefghij2"]
        assert all(i.entry["_yt"] for i in items(panel))
        assert not [c for c in panel._lv.children if isinstance(c, HeaderListItem)]


async def test_no_browser_says_so_and_fetches_nothing(app, fetched):
    shown = []
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._current_tab = "history:yt"
        panel = panel_of(app)
        panel.set_empty_message = shown.append
        screen._load_view("history:yt")
        await pilot.pause(0.5)
        assert not yt_calls(fetched)
        assert shown and "signed-in browser" in shown[0]


async def test_empty_result_has_a_specific_message(app, signed_in, monkeypatch):
    shown = []
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._current_tab = "history:yt"
        panel_of(app).set_empty_message = shown.append
        screen._load_view("history:yt")
        await pilot.pause(0.5)
        assert shown and shown[0].startswith("Nothing here.")


async def test_sign_in_failure_shows_the_sign_in_message_not_the_update_prompt(app, signed_in, monkeypatch):
    shown = []

    def boom(*a, **k):
        raise RuntimeError("Sign in to confirm")

    monkeypatch.setattr("src.ytdlp.fetch_page_batch", boom)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._prompt_ytdlp_update = lambda *a: shown.append("update")
        screen._current_tab = "history:yt"
        panel_of(app).set_error_message = shown.append
        screen._load_view("history:yt")
        await pilot.pause(0.5)
        assert len(shown) == 1 and "sign-in" in shown[0]


async def test_d_on_youtube_history_explains_and_removes_nothing(app, signed_in, fetched):
    hints = []
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._hint = lambda msg, *a: hints.append(msg)
        screen._current_tab = "history:yt"
        screen._load_view("history:yt")
        await pilot.pause(0.5)
        await pilot.press("D")
        assert hints and "not supported" in hints[0]
        assert len(items(panel_of(app))) == 2


async def test_i_imports_into_local_history_without_duplicates(app, signed_in, fetched):
    history.add({"id": "abcdefghij1", "title": "Local copy"})
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._current_tab = "history:yt"
        screen._load_view("history:yt")
        await pilot.pause(0.5)
        await pilot.press("I")
        rows = {r["id"]: r for r in history.all_entries()}
        assert rows["abcdefghij1"]["title"] == "Local copy" and rows["abcdefghij1"]["source"] == "local"
        assert rows["abcdefghij2"]["source"] == "yt" and rows["abcdefghij2"]["watched_at"] is None


async def test_i_and_y_outside_their_view_only_hint(app):
    hints = []
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._hint = lambda msg, *a: hints.append(msg)
        screen._current_tab = "home"
        await pilot.press("I")
        await pilot.press("Y")
        assert len(hints) == 2 and not history.all_entries()


def test_yt_badge_on_account_rows_and_imported_rows_only():
    def markup(entry):
        return VideoListItem({"id": "abcdefghij1", "title": "T", **entry})._build_markup()

    assert "YT" in markup({"_yt": True}) and "YT" in markup({"source": "yt"})
    assert "YT" not in markup({"source": "local"})


async def test_watch_later_is_the_third_source_and_read_only(app, signed_in, fetched):
    hints = []
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._hint = lambda msg, *a: hints.append(msg)
        screen.action_goto_tab("history")
        await pilot.pause(0.3)
        await pilot.press("Y")
        await pilot.press("Y")
        await pilot.pause(0.5)
        assert screen._current_tab == "history:wl"
        calls = [c for c in fetched if c[1]["feed_key"] == "yt_watchlater"]
        assert calls and calls[0][0] == "https://www.youtube.com/playlist?list=WL" and calls[0][1]["auth"] is True
        assert all(i.entry["_yt"] for i in items(panel_of(app)))
        await pilot.press("D")
        await pilot.press("I")
        assert "Watch Later" in hints[0] and len(hints) == 2 and not history.all_entries()
        await pilot.press("Y")
        await pilot.pause(0.3)
        assert screen._current_tab == "history"
