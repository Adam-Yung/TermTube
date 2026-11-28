"""History order by plays and watched time, and what its rows say about each."""

import pytest

from src import history
from src.tests.fakes import silence_detail_workers
from src.tests.tui.history_list import children, open_history, panel_of, rows
from src.tui.widgets.video_list import HeaderListItem


@pytest.fixture(autouse=True)
def no_detail_network(monkeypatch):
    silence_detail_workers(monkeypatch)


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
        assert shown and "search results" in shown[0] and "local history" in shown[0]
