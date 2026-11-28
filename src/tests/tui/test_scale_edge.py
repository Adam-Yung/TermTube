"""Scale and odd input: 5000 rows, odd playlist names, garbage filter queries, rows missing fields, hostile text."""

import time

import pytest
from textual.content import Content

from src import fuzzy, library_query, playlist
from src.search_stack import SearchStack
from src.tests.fakes import silence_detail_workers, silence_empty_feed_modal
from src.tui.fmt import escape_markup, fmt_day_group
from src.tui.widgets.video_list import VideoListItem, VideoListPanel

BUDGET_S = 30  # generous: a dozen full passes over 5000 rows take well under a second on a slow runner

HOSTILE = [
    "[x] [/y] \\",
    "trailing backslash \\",
    "\\[not a tag]",
    "[bold]unclosed",
    "🎵 emoji 👨‍👩‍👧 [🔥]",
    "שלום עולם [rtl] مرحبا",
    "x" * 500 + " [cut] tail",
]


def plain(markup: str) -> str:
    return Content.from_markup(markup).plain.replace("​", "")


def big(n=5000):
    return [
        {
            "id": f"v{i:010d}", "title": f"Lofi beats number {i} [mix]", "uploader": f"Channel {i % 40}",
            "duration": 60 + i, "view_count": i * 7, "upload_date": f"2024{(i % 12) + 1:02d}{(i % 28) + 1:02d}",
            "watched_at": 1_700_000_000 - i * 3600,
        }
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def quiet(monkeypatch, temp_history, temp_playlists):
    silence_detail_workers(monkeypatch)
    silence_empty_feed_modal(monkeypatch)
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])


async def test_a_5000_row_list_pages_filters_per_keystroke_marks_and_groups_days(app):
    entries = big()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(VideoListPanel)
        started = time.monotonic()
        panel.set_view_options(group_by=lambda e: fmt_day_group(e.get("watched_at")), show_count=True)
        panel.add_entries(1, entries, evict=False)
        panel.load_page(1)
        assert panel.total_pages == -(-5000 // panel.page_size) and panel.loaded_count == 5000
        panel.load_page(panel.total_pages, cursor="last")
        panel.load_page(1)
        for step in range(1, len("lofi beats 4999") + 1):  # one filter pass per keystroke
            panel._apply_filter("lofi beats 4999"[:step])
        assert [e["id"] for e in panel._filtered_pages[1]] == ["v0000004999"]
        panel._apply_filter("")
        for page in range(1, 6):
            panel.load_page(page)
            panel.mark_page()
        assert len(panel.marked_entries()) == 5 * panel.page_size
        assert time.monotonic() - started < BUDGET_S


@pytest.mark.parametrize(
    "matcher", [lambda e, q: fuzzy.rank(e, q), lambda e, q: library_query.rank(e, q, lambda *a: [])]
)
def test_ranking_5000_rows_with_garbage_queries_is_cheap_and_never_raises(matcher):
    entries = big()
    queries = ["", "(.*[", "[", "\\", "^$", "a|b", "dur:", "by:\"", "year:abc", "dur:>", "type:", "pl:", "dl:", "*",
               "?", 'by:"unclosed', "dur:99999999999999999999", "year:-5", "🎵", "x" * 5000]
    started = time.monotonic()
    for query in queries:
        assert isinstance(matcher(entries, query), list)
    assert time.monotonic() - started < BUDGET_S


def test_playlist_names_collide_after_strip_and_fold(temp_playlists):
    first = playlist.create("  Mix ")
    assert first and first["name"] == "Mix"
    assert playlist.create("mix") is None and playlist.create("MIX  ") is None and playlist.create("   ") is None
    other = playlist.create("Other")
    assert not playlist.rename(other["id"], " mIx ") and playlist.rename(other["id"], "  Other  ")
    assert playlist.rename(first["id"], "MIX") and playlist.find_by_name(" mix ")["id"] == first["id"]
    assert [p["name"] for p in playlist.list_playlists()] == ["MIX", "Other"]


def test_importing_playlists_that_collide_after_strip_keeps_every_one_with_a_distinct_name(temp_playlists):
    migrated = playlist._migrate({"Mix": [], " mix ": [], "MIX": [], "  ": [], "Other": []}, 1)
    names = [p["name"].casefold() for p in migrated["playlists"]]
    assert len(names) == len(set(names)) and len(names) == 4


@pytest.mark.parametrize(
    "entry",
    [
        {},
        {"id": "x"},
        {"id": "x", "title": None, "uploader": None, "duration": None, "view_count": None, "upload_date": None},
        {"id": "x", "duration": -5, "view_count": -1, "upload_date": "99999999", "watched_at": -10},
        {"id": "x", "duration": 10**15, "view_count": 10**30, "upload_date": "00000000", "watched_at": 10**15},
        {"id": "x", "upload_date": "yesterday", "plays": -3},
        {"id": "x", "_is_channel": True, "subscriber_count": -1, "video_count": 10**12},
        {"id": "x", "_is_playlist": True, "video_count": None},
    ],
)
def test_a_row_with_missing_or_absurd_fields_still_renders(entry):
    assert isinstance(plain(VideoListItem(entry)._build_markup()), str)


@pytest.mark.parametrize("text", HOSTILE)
def test_hostile_text_renders_as_text_in_rows_the_breadcrumb_and_the_search_hint(text):
    row = plain(VideoListItem({"id": "x", "title": text, "uploader": text})._build_markup())
    assert text[:30].replace("​", "") in row.replace("\n", " ") or text[:5] in row
    stack = SearchStack()
    stack.push(text)
    stack.push("second")
    assert text in plain(f"[dim]{escape_markup(stack.breadcrumb())}[/dim]")


@pytest.mark.parametrize("text", HOSTILE)
async def test_hostile_text_in_breadcrumbs_notices_and_the_detail_panel(app, text):
    from src.tui.widgets.detail_panel import DetailPanel

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(VideoListPanel)
        panel.set_breadcrumb(f"🎵 {text}")
        panel.set_notice(text)
        panel.set_progress(text)
        panel.set_empty_message(text)
        panel.set_error_message(text)
        app.notify(text)
        detail = app.screen.query_one(DetailPanel)
        entry = {"id": "AAAAAAAAAAA", "title": text, "uploader": text, "channel": text, "description": text}
        detail.update_basic(entry)
        detail.refresh_metadata(entry)
        await pilot.pause(0.2)
        crumb = str(panel.query_one("#list-breadcrumb").content)
        assert plain(crumb).startswith("🎵 ") and text[:5] in plain(crumb)
        assert app.is_running
