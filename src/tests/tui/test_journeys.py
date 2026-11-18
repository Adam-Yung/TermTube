"""Scripted journeys through the real screens with fake data: what the user sees at each step."""

import threading

import pytest
import yaml
from textual.widgets import Input
from textual.worker import WorkerCancelled

from src import history, playlist
from src.tui.audio_controller import AudioController
from src.tui.screens.queue_modal import QueueModal
from src.tui.widgets.video_list import VideoListPanel


def rows(prefix, n):
    return [
        {"id": f"{prefix}-{i}".ljust(11, "_"), "title": f"{prefix} title {i}", "uploader": "Chan", "duration": 120}
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def quiet(monkeypatch, temp_history, temp_playlists):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a: None)
    monkeypatch.setattr(AudioController, "_launch_worker", lambda *a, **k: None)
    monkeypatch.setattr("src.tui.audio_controller.cleanup_ipc", lambda path: None)


async def settle(app, pilot):
    for _ in range(3):
        try:
            await app.workers.wait_for_complete()
        except WorkerCancelled:
            pass
        await pilot.pause()


async def until(pilot, check):
    for _ in range(200):
        if check():
            return
        await pilot.pause()
    raise AssertionError("condition never became true")


def panel_of(app) -> VideoListPanel:
    return app.screen.query_one(VideoListPanel)


def shown(app) -> list[str]:
    return [e["id"] for e in panel_of(app).visited_entries()]


async def test_home_journey_load_page_extend_toggle_played_refresh(app, monkeypatch):
    fetches, extended = [], threading.Event()
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: fetches.append(1) or rows("home", 100))

    def more(panel):
        extended.set()
        return rows("more", 20)

    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        screen, panel = app.screen, panel_of(app)
        size = panel.page_size
        assert shown(app)[:2] == [e["id"] for e in rows("home", 2)] and panel.current_page == 1
        pages = panel.total_pages
        screen._fetch_next_batch = more
        assert pages >= 4
        for _ in range(pages - 3):  # up to the third-to-last page: nothing is requested yet
            await pilot.press("l")
        await pilot.pause()
        assert panel.current_page == pages - 2 and not extended.is_set()
        await pilot.press("l")  # the second-to-last page is shown: the feed grows behind it
        await until(pilot, extended.is_set)
        await settle(app, pilot)
        assert panel.total_pages > pages and shown(app)[-1] == rows("more", 20)[-1]["id"]
        assert panel.loaded_count == 100 + 20 and size == panel.page_size
        await pilot.press("Z")
        await settle(app, pilot)
        assert screen._show_played and panel.current_page == 1
        await pilot.press("Z")
        await settle(app, pilot)
        assert not screen._show_played
        before = len(fetches)
        await pilot.press("r")
        await settle(app, pilot)
        assert len(fetches) == before + 1 and shown(app)[0] == rows("home", 1)[0]["id"] and panel.current_page == 1


async def test_queue_journey_enqueue_three_then_reorder_remove_jump_and_close(app, monkeypatch):
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: rows("q", 6))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        controller = app.audio
        for _ in range(3):
            await pilot.press("e", "j")
        assert controller.entry["id"] == rows("q", 1)[0]["id"]
        assert [e["id"] for e in controller.queue] == [rows("q", 3)[i]["id"] for i in (1, 2)]
        await pilot.press("Q")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, QueueModal) and [k for k, _ in modal._rows] == ["now", "next", "next"]
        await pilot.press("down", "J")  # the first upcoming track moves below the second
        assert [e["id"] for e in controller.queue] == [rows("q", 3)[i]["id"] for i in (2, 1)]
        await pilot.press("D")
        assert [e["id"] for e in controller.queue] == [rows("q", 3)[2]["id"]]
        await pilot.press("u")
        assert len(controller.queue) == 2
        await pilot.press("enter")  # jumps to the highlighted upcoming track
        assert controller.entry["id"] in {rows("q", 3)[1]["id"], rows("q", 3)[2]["id"]} and len(controller.queue) == 1
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not modal and isinstance(app.screen.query_one(VideoListPanel), VideoListPanel)


async def test_quit_journey_flushes_history_and_stops_audio(app, monkeypatch, tmp_path):
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: rows("g", 3))
    stopped = []
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        history.add(rows("g", 1)[0], app.config)
        monkeypatch.setattr(app.audio, "stop_audio", lambda *a, **k: stopped.append(1))
        await pilot.press("q")
        await pilot.pause()
    assert stopped == [1] and not app.is_running
    on_disk = history.HISTORY_PATH.read_text(encoding="utf-8")
    assert rows("g", 1)[0]["id"] in on_disk


async def test_settings_journey_theme_rows_per_page_and_suggestions_persist(app, monkeypatch):
    from src.config import Config
    from src.tui.screens.settings_modal import SettingsModal, _Row

    monkeypatch.setattr("src.tui.screens.settings_modal.detect_installed_browsers", lambda: [])
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: rows("s", 60))

    def goto(modal, key):
        lv = modal._list
        row = next(c for c in lv.children if isinstance(c, _Row) and c.fld.key == key)
        lv.index = list(lv.children).index(row)

    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        panel = panel_of(app)
        size = panel.page_size
        await pilot.press("comma")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, SettingsModal)
        goto(modal, "search_suggestions")
        before = app.config.search_suggestions_enabled
        await pilot.press("enter")
        await pilot.pause()
        assert app.config.search_suggestions_enabled is (not before)
        goto(modal, "theme")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.press("j", "j", "enter")
        await pilot.pause(0.2)
        assert app.config.theme == "ocean" and app.has_class("theme-ocean")
        goto(modal, "rows_per_page")
        await pilot.press("enter")
        modal.query_one("#settings-input", Input).value = "35"
        await pilot.press("enter")
        assert app.config.rows_per_page == 35 and panel.page_size == size  # applies on the next load
        await pilot.press("escape")
        await pilot.pause()
        app.screen._load_view("home")
        await settle(app, pilot)
        assert panel_of(app).page_size == 35
    saved = yaml.safe_load(app.config.path.read_text(encoding="utf-8"))
    reloaded = Config(path=str(app.config.path))
    assert saved["rows_per_page"] == 35 and reloaded.rows_per_page == 35 and reloaded.theme == "ocean"
    assert reloaded.search_suggestions_enabled is (not before)


async def test_history_journey_play_resume_marker_remove_undo_source_switch_import(app, monkeypatch):
    from textual.content import Content

    from src.tui.widgets.video_list import VideoListItem

    yt = rows("yt", 4)
    monkeypatch.setattr("src.tui.screens.mixins.feed_loader.resolve_browser", lambda cfg: "chrome")
    monkeypatch.setattr(
        "src.ytdlp.fetch_page_batch", lambda *a, **k: yt if k.get("feed_key", "").startswith("yt_") else rows("h", 3)
    )
    async with app.run_test(size=(110, 34)) as pilot:
        await settle(app, pilot)
        controller, first = app.audio, rows("h", 3)[0]
        await pilot.press("a")  # plays the highlighted row's audio through the fake controller
        assert controller.entry["id"] == first["id"]
        controller._publish_progress(controller._session, 30.0, 120.0, False)
        controller._publish_progress(controller._session, 60.0, 120.0, False)
        controller._stop()
        await pilot.press("f4")
        await settle(app, pilot)
        screen = app.screen
        assert screen._current_tab == "history" and shown(app) == [first["id"]]
        row = next(c for c in panel_of(app)._lv.children if isinstance(c, VideoListItem))
        assert "▶ 1:00 / 2:00" in Content.from_markup(row._build_markup()).plain
        await pilot.press("D")
        assert screen._pending_remove is not None and history.get(first["id"])
        await pilot.press("y")
        await settle(app, pilot)
        assert history.get(first["id"]) is None and shown(app) == []
        await pilot.press("u")
        await settle(app, pilot)
        assert history.get(first["id"])["resume_s"] == 60 and shown(app) == [first["id"]]
        await pilot.press("Y")
        await settle(app, pilot)
        assert screen._current_tab == "history:yt" and shown(app) == [e["id"] for e in yt]
        await pilot.press("I")
        await pilot.pause()
        assert {e["id"] for e in history.all_entries()} == {first["id"], *(e["id"] for e in yt)}


async def test_search_journey_query_sort_type_channel_back_filter(app, monkeypatch):
    from src import innertube
    from src.tui.screens.channel_screen import ChannelScreen
    from src.tui.screens.search_modal import SearchModal
    from src.tui.screens.sort_modal import SortModal

    calls = []

    def results(query, config, cache, *, count=50, on_first_batch=None, sort="relevance", kind="all", **_):
        calls.append((query, sort, kind))
        return [
            {
                "id": f"{query[:3]}{i:08d}", "title": f"{query} {'cat' if i % 2 else 'dog'} {i}",
                "uploader": "Chan", "channel_url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            }
            for i in range(30)
        ]

    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    monkeypatch.setattr("src.ytdlp.fetch_search_batch", results)
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(innertube, "fetch_channel_page", lambda *a, **k: innertube.ChannelPage(rows("ch", 3)))

    async def search(text):
        await pilot.press("slash")
        await pilot.pause()
        assert isinstance(app.screen, SearchModal)
        await pilot.press(*text, "enter")
        await settle(app, pilot)

    async with app.run_test(size=(110, 34)) as pilot:
        await settle(app, pilot)
        screen = app.screen
        await search("alpha")
        assert screen._current_tab == "search" and calls[-1] == ("alpha", "relevance", "all")
        assert shown(app)[0].startswith("alp")
        await search("beta")
        assert shown(app)[0].startswith("bet") and "alpha" in str(panel_of(app)._breadcrumb.content)
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SortModal)
        await pilot.press("d")  # newest first
        await settle(app, pilot)
        assert screen._search.sort == "date" and calls[-1][1] == screen._search.sort
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, SortModal)
        await pilot.press("v")  # videos only
        await settle(app, pilot)
        assert screen._search.kind == "video" and calls[-1][2] == "video"
        await pilot.press("c")
        await settle(app, pilot)
        assert isinstance(app.screen, ChannelScreen)
        await pilot.press("escape")
        await settle(app, pilot)
        assert app.screen is screen and screen._search.query == "beta"
        await pilot.press("backspace")
        await settle(app, pilot)
        assert screen._search.query == "alpha" and shown(app)[0].startswith("alp")
        await pilot.press("f", "c", "a", "t")
        await pilot.pause()
        held = [e for page in panel_of(app)._filtered_pages.values() for e in page]
        assert held and all("cat" in e["title"] for e in held) and len(held) < 30


def add_download(directory, vid, ext, size=5):
    import json

    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{vid}.{ext}").write_bytes(b"x" * size)
    sidecar = {"id": vid, "title": f"Title {vid}", "upload_date": "20260101", "duration": 100, "uploader": "Chan"}
    (directory / f"{vid}.info.json").write_text(json.dumps(sidecar), encoding="utf-8")


async def test_library_journey_rail_playlist_reorder_remove_undo_rename_delete(app, monkeypatch, tmp_path):
    from textual.content import Content

    from src.tui.screens.name_modal import NameModal
    from src.tui.widgets.action_bar import ActionBar

    videos, audio = tmp_path / "vid", tmp_path / "aud"
    add_download(videos, "v1", "mp4")
    add_download(videos, "v2", "mp4", size=2000)
    add_download(audio, "a1", "mp3", size=40)
    app.config._data["video_dir"], app.config._data["audio_dir"] = str(videos), str(audio)
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: [])
    questions = []
    real_prompt = ActionBar.show_prompt

    def spy(self, question):
        questions.append(Content.from_markup(question).plain)
        real_prompt(self, question)

    monkeypatch.setattr(ActionBar, "show_prompt", spy)

    async def name_it(name):
        assert isinstance(app.screen, NameModal)
        app.screen.query_one("#name-input", Input).value = name
        await app.screen.query_one("#name-input", Input).action_submit()
        await settle(app, pilot)

    async with app.run_test(size=(120, 40)) as pilot:
        await settle(app, pilot)
        screen = app.screen
        await pilot.press("f5")
        await settle(app, pilot)
        assert sorted(shown(app)) == ["a1", "v1", "v2"]
        screen._select_collection("library:video", focus_list=True)
        await settle(app, pilot)
        assert sorted(shown(app)) == ["v1", "v2"]
        screen._select_collection("library:audio", focus_list=True)
        await settle(app, pilot)
        assert shown(app) == ["a1"]
        await pilot.press("n")  # a playlist from the rail
        await pilot.pause()
        await name_it("Mix")
        record = playlist.list_playlists()[0]
        pview = f"playlist:{record['id']}"
        assert screen._current_tab == pview and shown(app) == []
        screen._select_collection("library:video", focus_list=True)
        await settle(app, pilot)
        for _ in range(2):  # add each row through the picker (Enter flips the highlighted playlist on)
            await pilot.press("p")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.press("j")
        order = [i["id"] for i in playlist.get(record["id"])["items"]]
        assert sorted(order) == ["v1", "v2"]
        screen._select_collection(pview, focus_list=True)
        await settle(app, pilot)
        assert shown(app) == order
        await pilot.press("J")
        assert [i["id"] for i in playlist.get(record["id"])["items"]] == order[::-1]
        await pilot.press("D", "y")
        await settle(app, pilot)
        assert len(playlist.get(record["id"])["items"]) == 1
        await pilot.press("u")
        await settle(app, pilot)
        assert sorted(i["id"] for i in playlist.get(record["id"])["items"]) == ["v1", "v2"]
        await pilot.press("R")
        await pilot.pause()
        await name_it("Mix tape")
        assert playlist.get(record["id"])["name"] == "Mix tape"
        screen._select_collection("library:video", focus_list=True)  # delete a downloaded row: the question lists it
        await settle(app, pilot)
        await pilot.press("D")
        assert questions[-1].startswith('Delete "Title ') and "video" in questions[-1]
        await pilot.press("n")  # any other key cancels
        assert (videos / "v1.mp4").exists() and (videos / "v2.mp4").exists()
        screen._rail().focus()
        screen._select_collection(pview, focus_list=False)
        await settle(app, pilot)
        await pilot.press("D", "y")
        await settle(app, pilot)
        assert playlist.get(record["id"]) is None
        assert (videos / "v1.mp4").exists() and (videos / "v2.mp4").exists()  # a playlist delete never touches files
