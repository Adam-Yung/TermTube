"""Queue operations on AudioController, the queue page, and resume/watch-time through the controller."""

import asyncio
from unittest.mock import patch

import pytest
from textual.screen import Screen

from src import history, player
from src.strings import text
from src.tests.fakes import silence_detail_workers
from src.tui.audio_controller import AudioController
from src.tui.messages import PlayerStateUpdated
from src.tui.screens.queue_screen import QueueScreen
from src.tui.widgets.video_list import VideoListItem

A = {"id": "AAAAAAAAAAA", "title": "Playing", "uploader": "U", "duration": 600}
B = {"id": "BBBBBBBBBBB", "title": "Second", "duration": 100}
C = {"id": "CCCCCCCCCCC", "title": "Third"}
D = {"id": "DDDDDDDDDDD", "title": "Fourth"}


class Recorder(Screen):
    def __init__(self):
        super().__init__()
        self.queue_lens = []

    def on_audio_queue_changed(self, message):
        self.queue_lens.append(message.queue_len)


@pytest.fixture
def audio(app, mock_mpv_ipc, tmp_path, monkeypatch):
    monkeypatch.setattr("src.history.HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(AudioController, "_launch_worker", lambda *a, **k: None)
    monkeypatch.setattr("src.tui.audio_controller.cleanup_ipc", lambda path: None)
    silence_detail_workers(monkeypatch)
    return app


def ids(controller):
    return [e["id"][0] for e in controller.queue]


def playing(controller, *queued):
    controller._play_pending = True
    controller._entry = A
    controller._queue = list(queued)


async def test_move_clamps_returns_the_new_index_and_broadcasts(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        controller = audio.audio
        playing(controller, B, C, D)
        seen = Recorder()
        await audio.push_screen(seen)
        assert controller.move_queued(0, 1) == 1 and ids(controller) == ["C", "B", "D"]
        assert controller.move_queued(1, 5) == 2 and ids(controller) == ["C", "D", "B"]
        assert controller.move_queued(1, -9) == 0 and ids(controller) == ["D", "C", "B"]
        assert controller.move_queued(0, -1) == 0 and controller.move_queued(7, 1) == 7
        assert controller.move_queued(-1, 1) == -1 and ids(controller) == ["D", "C", "B"]
        await pilot.pause(0.1)
        assert seen.queue_lens == [3, 3, 3]  # a no-op does not broadcast


async def test_remove_returns_the_entry_and_refuses_out_of_range(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        playing(controller, B, C)
        assert controller.remove_queued(5) is None and controller.remove_queued(-1) is None
        assert controller.remove_queued(0) is B and ids(controller) == ["C"]
        assert controller.entry is A


async def test_insert_puts_back_at_the_index_and_never_duplicates(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        playing(controller, B, D)
        controller.insert_queued(1, C)
        assert ids(controller) == ["B", "C", "D"]
        controller.insert_queued(0, C)
        controller.insert_queued(0, A)
        assert ids(controller) == ["B", "C", "D"]
        controller.insert_queued(99, {"id": "EEEEEEEEEEE"})
        controller.insert_queued(-5, {"id": "FFFFFFFFFFF"})
        assert ids(controller) == ["F", "B", "C", "D", "E"]


async def test_play_queued_starts_that_track_and_keeps_the_ones_before_it(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        playing(controller, B, C, D)
        with patch.object(controller, "play_audio") as play:
            controller.play_queued(1)
            controller.play_queued(9)
        play.assert_called_once_with(C)
        assert ids(controller) == ["B", "D"]


async def test_q_when_idle_opens_the_empty_page_and_q_closes_it(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.8)
        main = audio.screen
        await pilot.press("q")
        await pilot.pause(0.3)
        page = audio.screen
        assert isinstance(page, QueueScreen) and titles(page) == []
        assert text("queue_screen.empty") in str(page.query_one("#list-message").content)
        await pilot.press("D", "J", "c", "u", "enter")
        await pilot.press("q")
        await pilot.pause(0.2)
        assert audio.screen is main and audio.is_running


async def open_queue(audio, pilot, *queued):
    await pilot.pause(0.8)
    playing(audio.audio, *queued)
    await pilot.press("q")
    await pilot.pause(0.3)
    assert isinstance(audio.screen, QueueScreen)
    return audio.screen


def titles(page):
    return [item.entry["title"] for item in page.query(VideoListItem)]


def cursor(page):
    entry = page._selected_entry()
    return entry["title"] if entry else None


async def press(pilot, *keys):
    for key in keys:
        await pilot.press(key)
        await pilot.pause(0.15)


async def test_q_opens_the_page_with_the_playing_track_first_and_badged(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        page = await open_queue(audio, pilot, B, C)
        assert titles(page) == ["Playing", "Second", "Third"] and cursor(page) == "Playing"
        assert [item.playing for item in page.query(VideoListItem)] == [True, False, False]
        assert "Queue · 2 up next" in str(page.query_one("#list-breadcrumb").content)


async def test_reorder_remove_and_undo_on_the_page(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        page = await open_queue(audio, pilot, B, C, D)
        await press(pilot, "j", "J")  # Second moves down; the cursor follows it
        assert ids(audio.audio) == ["C", "B", "D"] and cursor(page) == "Second"
        await press(pilot, "K", "K")
        assert ids(audio.audio) == ["B", "C", "D"] and cursor(page) == "Second"
        await press(pilot, "j", "D")  # remove Third; the cursor stays on its row
        assert ids(audio.audio) == ["B", "D"] and cursor(page) == "Fourth"
        await press(pilot, "D")
        assert ids(audio.audio) == ["B"]
        await press(pilot, "u")
        assert ids(audio.audio) == ["B", "D"]
        await press(pilot, "u")
        assert ids(audio.audio) == ["B", "C", "D"] and cursor(page) == "Third"
        await press(pilot, "u")
        assert ids(audio.audio) == ["B", "C", "D"]


async def test_c_clears_the_upcoming_tracks_and_u_brings_them_back(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        page = await open_queue(audio, pilot, B, C, D)
        await press(pilot, "c")
        assert ids(audio.audio) == [] and audio.audio.entry is A and titles(page) == ["Playing"]
        await press(pilot, "u")
        assert ids(audio.audio) == ["B", "C", "D"] and titles(page) == ["Playing", "Second", "Third", "Fourth"]


async def test_the_playing_track_cannot_be_moved_or_removed(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        page = await open_queue(audio, pilot, B, C)
        shown = []
        with patch.object(page, "notify", lambda msg, **kw: shown.append(msg)):
            await press(pilot, "D", "J", "K", "enter")
        assert ids(audio.audio) == ["B", "C"] and audio.audio.entry is A
        assert shown == [text("queue_screen.is_playing"), text("queue_screen.already_playing")]


@pytest.mark.parametrize("key", ["enter", "a"])
async def test_enter_and_a_play_the_highlighted_upcoming_track_now(audio, key):
    async with audio.run_test(size=(100, 30)) as pilot:
        page = await open_queue(audio, pilot, B, C)
        with patch.object(audio.audio, "play_audio") as play:
            await press(pilot, "j", "j", key)
        play.assert_called_once_with(C)
        assert ids(audio.audio) == ["B"] and audio.screen is page


async def test_the_page_follows_the_queue_while_open(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        page = await open_queue(audio, pilot, B)
        await press(pilot, "j")
        audio.audio._queue.append(C)
        audio.audio._queue_changed()
        await pilot.pause(0.3)
        assert titles(page) == ["Playing", "Second", "Third"] and cursor(page) == "Second"
        audio.audio._queue.pop(0)  # the first upcoming track started elsewhere: the cursor keeps its row
        audio.audio._queue_changed()
        await pilot.pause(0.3)
        assert titles(page) == ["Playing", "Third"] and cursor(page) == "Third"
        audio.audio._entry, audio.audio._play_pending = None, False
        audio.audio._queue.clear()
        audio.audio._broadcast(lambda: PlayerStateUpdated(0.0, 0.0, False, playing=False))
        await pilot.pause(0.3)
        assert titles(page) == [] and page.query_one("#list-message").display


async def test_a_long_queue_keeps_the_cursor_across_pages(audio):
    many = [{"id": f"x{i:010d}", "title": f"T{i}"} for i in range(60)]
    async with audio.run_test(size=(100, 30)) as pilot:
        page = await open_queue(audio, pilot, *many)
        await press(pilot, "G")
        assert cursor(page) == "T59"
        await press(pilot, "K")
        assert ids(audio.audio)[-2:] == ["x", "x"] and audio.audio.queue[-2]["title"] == "T59"
        assert cursor(page) == "T59"


async def test_starting_a_queued_track_takes_it_out_of_the_queue(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        playing(controller, B, C)
        controller.play_audio(C)
        assert controller.entry is C and ids(controller) == ["B"]


async def test_clear_queue_returns_what_it_removed_and_broadcasts_once(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        controller = audio.audio
        playing(controller, B, C)
        seen = Recorder()
        await audio.push_screen(seen)
        assert controller.clear_queue() == [B, C] and controller.clear_queue() == []
        await pilot.pause(0.1)
        assert seen.queue_lens == [0] and controller.entry is A


def publish(controller, positions, dur=600.0):
    for pos in positions:
        controller._publish_progress(controller._session, pos, dur, False)


async def test_playing_records_time_and_the_resume_point_when_stopped(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        controller.play_audio(A)
        publish(controller, [i * 0.5 for i in range(0, 61)])  # 30 s of half-second polls
        controller._stop()
        record = history.get(A["id"])
        assert record["resume_s"] == 30 and round(record["seconds"]) == 30 and record["plays"] == 1


async def test_a_track_that_plays_to_the_end_loses_its_resume_point(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        controller.play_audio(A)
        publish(controller, [i * 0.5 for i in range(0, 41)])
        controller._stop()
        assert history.get(A["id"])["resume_s"] == 20
        controller.play_audio(A)
        publish(controller, [20, 20.5, 21])
        controller._proc = None
        controller._on_finished(A, controller._session)
        assert history.get(A["id"])["resume_s"] is None


async def test_switching_tracks_saves_the_old_one_first(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        controller.play_audio(A)
        publish(controller, [i * 0.5 for i in range(0, 41)])
        controller.play_audio(B)
        publish(controller, [0, 0.5])
        assert history.get(A["id"])["resume_s"] == 20 and history.get(B["id"])["resume_s"] is None


async def test_resume_is_passed_to_mpv_as_start_and_announced(audio, monkeypatch):
    history.add(A)
    history.record_progress(A["id"], resume_s=125, watched=0)
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        built, notices = [], []
        monkeypatch.setattr(player, "run_mpv_with_retries",
                            lambda build_cmd, **kw: built.append(build_cmd(1)) or player.MpvOutcome("stale"))
        monkeypatch.setattr(audio, "notify", lambda msg, **kw: notices.append(msg))
        controller._session = 1
        await asyncio.to_thread(controller._play_with_retries, A, 1, "mpv", "in.conf", "http://s", "")
        await asyncio.sleep(0.1)
        assert "--start=125" in built[0] and text("audio_controller.resuming", clock="2:05") in notices
        audio.config.set("resume_playback", False)
        built.clear()
        await asyncio.to_thread(controller._play_with_retries, A, 1, "mpv", "in.conf", "http://s", "")
        assert not any(a.startswith("--start") for a in built[0])
