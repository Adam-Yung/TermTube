"""Settings modal: sections, navigation, inline editing with refusals, reset, reload from disk, clear actions."""

import sys

import pytest
import yaml
from textual.widgets import Input

from src.tui.screens.quality_modal import QualityModal
from src.tui.screens.settings_modal import SettingsModal, _Row
from src.tui.settings_fields import FIELDS, SECTIONS


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr("src.history.HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.browsers.detect_installed_browsers", lambda: [{"name": "firefox", "label": "Firefox"}])
    monkeypatch.setattr("src.tui.screens.settings_modal.detect_installed_browsers",
                        lambda: [{"name": "firefox", "label": "Firefox"}])


async def open_settings(app, pilot) -> SettingsModal:
    app.push_screen(SettingsModal())
    await pilot.pause(0.3)
    return app.screen


def goto(modal: SettingsModal, key: str) -> _Row:
    lv = modal._list
    row = next(c for c in lv.children if isinstance(c, _Row) and c.fld.key == key)
    lv.index = list(lv.children).index(row)
    return row


def status(modal) -> str:
    return str(modal.query_one("#settings-status").content)


def on_disk(app) -> dict:
    return yaml.safe_load(app.config.path.read_text(encoding="utf-8"))


async def test_every_section_has_rows_and_headers_are_skipped_by_the_cursor(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        kids = list(modal._list.children)
        assert {s for s in SECTIONS} == {k._title for k in kids if hasattr(k, "_title")}
        assert sum(isinstance(k, _Row) for k in kids) == len(FIELDS)
        first = modal._list.highlighted_child
        assert isinstance(first, _Row) and first.fld is FIELDS[0]
        await pilot.press("j")
        assert modal._list.highlighted_child.fld is FIELDS[1]
        await pilot.press("k", "k")
        assert modal._list.highlighted_child.fld is FIELDS[0]


async def test_tab_jumps_between_sections_and_wraps(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        seen = []
        for _ in range(len(SECTIONS)):
            await pilot.press("tab")
            seen.append(modal._list.highlighted_child.fld.section)
        assert seen == [*SECTIONS[1:], SECTIONS[0]]
        await pilot.press("shift+tab")
        assert modal._list.highlighted_child.fld.section == SECTIONS[-1]


async def test_booleans_toggle_with_enter_and_space_and_persist(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "sponsorblock.enabled")
        await pilot.press("enter")
        assert app.config.sponsorblock_enabled is False
        assert on_disk(app)["sponsorblock"]["enabled"] is False
        await pilot.press("space")
        assert app.config.sponsorblock_enabled is True
        assert on_disk(app)["sponsorblock"]["enabled"] is True
        goto(modal, "history")
        await pilot.press("enter")
        assert app.config.history_enabled is False and on_disk(app)["history"] is False


async def test_a_choice_opens_the_picker_and_saves_the_pick(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "preferred_quality")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, QualityModal)
        await pilot.press("j", "j", "enter")
        await pilot.pause(0.2)
        assert app.screen is modal and app.config.preferred_quality == "720"
        assert on_disk(app)["preferred_quality"] == "720"


async def test_theme_pick_restyles_the_app_at_once(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "theme")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.press("j", "j", "enter")
        await pilot.pause(0.2)
        assert app.config.theme == "ocean" and app.has_class("theme-ocean") and not app.has_class("theme-crimson")


async def test_the_browser_picker_lists_detected_browsers_and_the_account_line_follows(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        info = next(r for r in modal._list.query(_Row) if r.fld.key == "resolved_browser")
        assert "no cookies" in str(info.query_one("Static").content)
        goto(modal, "browser")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, QualityModal)
        await pilot.press("j", "enter")
        await pilot.pause(0.2)
        assert app.config.get("browser") == "firefox"
        assert "firefox" in str(info.query_one("Static").content) and "cookies from this browser" in str(
            info.query_one("Static").content
        )


async def test_a_valid_directory_is_saved_and_the_input_closes(app, tmp_path):
    target = tmp_path / "new" / "videos"
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "video_dir")
        await pilot.press("enter")
        field = modal.query_one("#settings-input", Input)
        assert field.display and field.has_focus
        field.value = str(target)
        await pilot.press("enter")
        assert app.config.video_dir == target and on_disk(app)["video_dir"] == str(target)
        assert not field.display and modal._list.has_focus


@pytest.mark.parametrize(("key", "text", "reason"), [
    ("video_format", "../escape/%(title)s.%(ext)s", "relative path without '..'"),
    ("audio_format", "/abs/%(title)s.%(ext)s", "relative path without '..'"),
    ("video_dir", "relative/dir", "absolute path"),
    ("rows_per_page", "5", "from 10 to 50"),
    ("rows_per_page", "many", "whole number"),
    ("history_max", "10", "from 50 to 5000"),
    ("sponsorblock.categories", "sponsor, bogus", "Unknown: bogus"),
    ("cache_ttl.home", "1", "from 60"),
])
async def test_an_invalid_value_is_refused_with_a_reason_and_nothing_is_saved(app, key, text, reason):
    before = app.config.get(key)
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, key)
        await pilot.press("enter")
        field = modal.query_one("#settings-input", Input)
        field.value = text
        await pilot.press("enter")
        assert reason in status(modal)
        assert field.display and app.config.get(key) == before


async def test_a_file_and_an_unwritable_directory_are_refused(app, tmp_path):
    not_a_dir = tmp_path / "plain.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    locked = tmp_path / "locked"
    locked.mkdir()
    posix_modes = sys.platform != "win32"  # Windows ignores directory permission bits
    if posix_modes:
        locked.chmod(0o500)
    try:
        async with app.run_test(size=(110, 50)) as pilot:
            modal = await open_settings(app, pilot)
            goto(modal, "audio_dir")
            await pilot.press("enter")
            field = modal.query_one("#settings-input", Input)
            field.value = str(not_a_dir / "sub")
            await pilot.press("enter")
            assert "is a file, not a directory" in status(modal)
            if posix_modes:
                field.value = str(locked / "sub")
                await pilot.press("enter")
                assert "is not writable" in status(modal)
    finally:
        locked.chmod(0o700)


async def test_typing_in_a_field_is_not_taken_by_the_list_keys(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        row = goto(modal, "video_format")
        await pilot.press("enter")
        field = modal.query_one("#settings-input", Input)
        field.value = ""
        await pilot.press("j", "k", "space", "x", "backspace")
        assert field.value == "jk "
        assert modal._list.highlighted_child is row


async def test_escape_cancels_an_edit_before_it_closes_the_dialog(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "history_max")
        await pilot.press("enter")
        await pilot.press("escape")
        assert app.screen is modal and not modal.query_one("#settings-input", Input).display
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.screen is not modal


async def test_backspace_puts_a_row_back_to_its_default(app):
    app.config.set("history_max", 100)
    app.config.set("sponsorblock.auto_skip", False)
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "history_max")
        await pilot.press("backspace")
        assert app.config.history_max == 500 and on_disk(app)["history_max"] == 500
        goto(modal, "sponsorblock.auto_skip")
        await pilot.press("backspace")
        assert app.config.sponsorblock_auto_skip is True


async def test_rows_per_page_is_set_from_the_dialog(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "rows_per_page")
        await pilot.press("enter")
        modal.query_one("#settings-input", Input).value = "35"
        await pilot.press("enter")
        assert app.config.rows_per_page == 35 and on_disk(app)["rows_per_page"] == 35
        assert "next list load" in status(modal)


async def test_cache_ttl_edit_reaches_the_live_cache(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "cache_ttl.metadata")
        await pilot.press("enter")
        modal.query_one("#settings-input", Input).value = "120"
        await pilot.press("enter")
        assert app.cache._ttl["metadata"] == 120


async def test_reload_reads_the_file_and_keeps_unknown_keys(app):
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        text = yaml.dump({"theme": "ocean", "future_key": 7, "cache_ttl": {"home": 99}})
        app.config.path.write_text(text, encoding="utf-8")
        goto(modal, "reload")
        await pilot.press("enter")
        assert app.config.theme == "ocean" and app.has_class("theme-ocean")
        assert app.cache._ttl["home"] == 99 and app.cache._ttl["search"] == 1800
        assert "Reloaded" in status(modal)
        goto(modal, "history")
        await pilot.press("enter")
        assert on_disk(app)["future_key"] == 7


async def test_reload_of_a_corrupted_file_reports_and_keeps_memory(app):
    app.config.set("theme", "amber")
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        app.config.path.write_text("theme: [unclosed\n  - : :", encoding="utf-8")
        goto(modal, "reload")
        await pilot.press("enter")
        assert "Reload failed" in status(modal) and "Keeping the settings in memory" in status(modal)
        assert app.config.theme == "amber"
        app.config.path.write_text("- just\n- a list\n", encoding="utf-8")
        await pilot.press("enter")
        assert "mapping" in status(modal) and app.config.theme == "amber"


async def test_a_change_that_cannot_be_written_says_so(app, monkeypatch):
    monkeypatch.setattr(type(app.config), "save", lambda self: False)
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "prefetch_video")
        await pilot.press("enter")
        assert app.config.prefetch_video_enabled is True
        assert "Could not write the config file" in status(modal)


async def test_clear_history_needs_a_second_enter(app, tmp_path):
    from src import history, search_history

    history.add({"id": "abc12345678", "title": "T", "uploader": "U"})
    search_history.add("python")
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "clear_history")
        await pilot.press("enter")
        assert "again to confirm" in status(modal) and history.all_entries()
        await pilot.press("j", "k", "enter")
        assert history.all_entries()
        await pilot.press("enter")
        assert not history.all_entries() and search_history.all_queries()
        goto(modal, "clear_search_history")
        await pilot.press("enter", "enter")
        assert not search_history.all_queries()


async def test_clear_cache_removes_cached_files_after_confirmation(app, tmp_path):
    feed = tmp_path / "feed_home.json"
    feed.write_text("[]", encoding="utf-8")
    thumb = tmp_path / "thumbs" / "a.jpg"
    thumb.write_bytes(b"x")
    async with app.run_test(size=(110, 50)) as pilot:
        modal = await open_settings(app, pilot)
        goto(modal, "clear_cache")
        await pilot.press("enter")
        assert feed.exists()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause(0.1)
        assert not feed.exists() and not thumb.exists()
        assert "Cache cleared" in status(modal)
