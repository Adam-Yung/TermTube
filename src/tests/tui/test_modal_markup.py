"""Titles and error text that look like markup show as typed in the dialogs."""
from textual.app import App
from textual.widgets import Static

from src.tui.screens.download_picker_modal import DownloadPickerModal
from src.tui.screens.ytdlp_update_modal import YtdlpUpdateModal

HOSTILE = "ERROR: [youtube] a [/x] b"


async def shown(modal, selector):
    app = App()
    async with app.run_test(size=(100, 30)) as pilot:
        app.push_screen(modal)
        await pilot.pause()
        return str(app.screen.query_one(selector, Static).render())


async def test_the_download_picker_shows_a_title_with_brackets():
    assert HOSTILE in await shown(DownloadPickerModal(HOSTILE), "#dlpick-video-title")


async def test_the_update_dialog_shows_an_error_with_brackets():
    assert HOSTILE in await shown(YtdlpUpdateModal(HOSTILE), "#ytdlp-update-body")
