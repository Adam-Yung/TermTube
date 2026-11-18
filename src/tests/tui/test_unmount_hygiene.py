"""Leaving the main screen must not leave the audio controller pointing at it."""

from src.tui.audio_controller import _no_log
from src.tui.screens.main_screen import MainScreen


async def test_the_audio_log_points_at_the_main_screen_only_while_it_lives(app, monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr(MainScreen, "_show_empty_feed_modal", lambda *a: None)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        assert app.audio.log == screen._log
        app.audio.detach_log(lambda _m: None)
        assert app.audio.log == screen._log
        screen.on_unmount()
        assert app.audio.log is _no_log
        await pilot.pause()
