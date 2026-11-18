"""Each typed source error reaches the Home list as its own message; an empty feed still opens the empty modal."""

import pytest

from src.errors import ExtractionFailed, NetworkDown, RateLimited, SignInRequired
from src.tui.widgets.video_list import VideoListPanel


@pytest.fixture(autouse=True)
def quiet(monkeypatch, temp_history):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)


@pytest.mark.parametrize(
    "exc, expect",
    [
        (NetworkDown("x"), "Network error · r to retry"),
        (RateLimited("x"), "rate limiting this IP"),
        (SignInRequired("x"), "Settings"),
    ],
)
async def test_typed_errors_show_their_message(app, monkeypatch, exc, expect):
    shown, prompts = [], []

    def boom(*a, **k):
        raise exc

    monkeypatch.setattr("src.ytdlp.fetch_page_batch", boom)
    monkeypatch.setattr(VideoListPanel, "set_error_message", lambda self, msg: shown.append(msg))
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._prompt_ytdlp_update", lambda *a: prompts.append(a))
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.5)
    assert shown and expect in shown[0] and not prompts


async def test_extraction_error_opens_the_update_prompt_only(app, monkeypatch):
    shown, prompts = [], []

    def boom(*a, **k):
        raise ExtractionFailed("Unable to extract")

    monkeypatch.setattr("src.ytdlp.fetch_page_batch", boom)
    monkeypatch.setattr(VideoListPanel, "set_error_message", lambda self, msg: shown.append(msg))
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._prompt_ytdlp_update", lambda *a: prompts.append(a))
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.5)
    assert prompts and not shown


async def test_empty_but_ok_feed_still_opens_the_empty_modal(app, monkeypatch):
    modals, shown = [], []
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    monkeypatch.setattr(VideoListPanel, "set_error_message", lambda self, msg: shown.append(msg))
    monkeypatch.setattr(
        "src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda self, key: modals.append(key)
    )
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.5)
    assert modals == ["home"] and not shown
