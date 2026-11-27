"""TUI interaction tests for MainScreen navigation."""

import pytest


async def test_app_boots_without_crash(app):
    """The app should start and compose without errors."""
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        assert app.screen is not None


async def test_app_has_video_list(app):
    """After boot, the VideoListPanel widget should exist in the DOM."""
    from src.tui.widgets.video_list import VideoListPanel

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.5)
        panel = app.screen.query_one("#video-list-panel", VideoListPanel)
        assert panel is not None


@pytest.mark.parametrize("opens", [(), ("q",), ("question_mark",)], ids=["main", "queue", "dialog"])
async def test_ctrl_q_quits_through_the_cleanup_from_anywhere(app, monkeypatch, opens):
    stopped = []
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        monkeypatch.setattr(app.audio, "stop_audio", lambda *a, **k: stopped.append(1))
        await pilot.press(*opens, "ctrl+q")
        await pilot.pause(0.2)
    assert stopped == [1] and not app.is_running


async def test_quit_flushes_the_deferred_history_write(app, monkeypatch):
    flushed = []
    monkeypatch.setattr("src.history.flush", lambda: flushed.append(True))
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("ctrl+q")
        await pilot.pause(0.1)
    assert flushed


async def test_help_toggle(app):
    """Pressing ? should push the HelpScreen."""
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("question_mark")
        await pilot.pause(0.2)
        screen_names = [type(s).__name__ for s in app.screen_stack]
        assert "HelpScreen" in screen_names, f"HelpScreen not in screen_stack: {screen_names}"


async def test_search_modal_opens(app):
    """Pressing / should open the search modal."""
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.5)
        await pilot.press("slash")
        await pilot.pause(1.0)
        screen_names = [type(s).__name__ for s in app.screen_stack]
        assert "SearchModal" in screen_names, f"SearchModal not in screen_stack: {screen_names}"
