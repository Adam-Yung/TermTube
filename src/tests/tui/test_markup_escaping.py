"""Titles with [brackets] must render as text, not as markup (seen live: 'Relax /…[/bold white]')."""

import pytest
from textual.content import Content

from src.tui.fmt import escape_markup
from src.tui.widgets.video_list import VideoListItem

TITLES = [
    "Best of lofi hip hop 2021 ✨ [beats to relax/study to] 6 hours",
    "x" * 70 + " [cut here] tail",
    "[PAUSED]",
    "unclosed [bracket",
]


def plain(markup: str) -> str:
    return Content.from_markup(markup).plain


@pytest.mark.parametrize("title", TITLES)
def test_escape_round_trips(title):
    assert plain(f"[bold]{escape_markup(title)}[/bold]") == title


@pytest.mark.parametrize("title", TITLES)
def test_list_row_shows_the_title_text(title):
    row = plain(VideoListItem({"id": "AAAAAAAAAAA", "title": title, "uploader": "Chan [x]"})._build_markup())
    assert "[/bold" not in row and "Chan [x]" in row
    assert row.splitlines()[0].startswith(title[:40])


async def test_now_playing_bar_shows_brackets_and_hints(app):
    async with app.run_test(size=(120, 40)) as pilot:
        bar = app.screen.query_one("#detail-panel").action_bar
        bar.set_player_mode({"title": "Lofi [beats] mix", "uploader": "Girl [live]"}, queue_len=0)
        bar.update_progress(5.0, 100.0, True)
        await pilot.pause(0.2)
        title = str(bar.query_one("#np-title-line").content)
        time_line = str(bar.query_one("#np-time-line").content)
        keys = str(bar.query_one("#np-keys").content)
    assert "[/bold" not in plain(title)
    assert "Lofi [beats] mix" in plain(title) and "Girl [live]" in plain(title)
    assert "[PAUSED]" in plain(time_line)
    assert "[/] ±5s" in plain(keys)


async def test_watch_modal_hint_shows_plain_brackets(app):
    from src.tui.screens.watch_modal import WatchModal

    async with app.run_test(size=(120, 40)) as pilot:
        modal = WatchModal({"id": "AAAAAAAAAAA", "title": "T [x]"}, ytdl_format="")
        modal._launch_video = lambda: None
        app.push_screen(modal)
        await pilot.pause(0.2)
        hint = plain(str(modal.query_one("#np-hint").content))
        title = plain(str(modal.query_one("#np-title").content))
        app.pop_screen()
    assert "[ ] ±5 s" in hint and "\\" not in hint and title == "T [x]"


@pytest.mark.parametrize("text", ["ends with a backslash \\", "a\\[b] c", "\\\\", "[/y] \\"])
def test_a_backslash_never_swallows_the_next_tag(text):
    out = plain(f"[bold]{escape_markup(text)}[/bold] tail")
    assert out.replace("​", "") == f"{text} tail"
