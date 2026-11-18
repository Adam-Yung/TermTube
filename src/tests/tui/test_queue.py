"""Queue operations on AudioController, the Q queue modal, and resume/watch-time through the controller."""

import asyncio
from unittest.mock import patch

import pytest
from textual.screen import Screen

from src import history, player
from src.tui.audio_controller import AudioController
from src.tui.screens.queue_modal import QueueModal

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
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
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


async def test_q_when_idle_is_a_hint_and_opens_no_modal(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.8)
        shown = []
        screen = audio.screen
        with patch.object(screen, "notify", lambda msg, **kw: shown.append(msg)):
            await pilot.press("Q")
            await pilot.pause(0.1)
        assert shown == ["Nothing playing."] and not isinstance(audio.screen, QueueModal)


async def open_queue(audio, pilot, *queued):
    await pilot.pause(0.8)
    playing(audio.audio, *queued)
    await pilot.press("Q")
    await pilot.pause(0.2)
    assert isinstance(audio.screen, QueueModal)
    return audio.screen


def titles(modal):
    return [str(modal._list.get_option_at_index(i).prompt).split("  ")[0] for i in range(modal._list.option_count)]


async def test_q_opens_the_queue_with_the_playing_track_first(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        modal = await open_queue(audio, pilot, B, C)
        assert titles(modal) == ["▶ Playing", "1. Second", "2. Third"]
        assert modal._list.highlighted == 0
        assert str(modal.query_one("#queue-title").content) == "Queue · 2 up next"


async def test_reorder_remove_and_undo_in_the_modal(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        modal = await open_queue(audio, pilot, B, C, D)
        await pilot.press("j", "J")  # Second moves down; the cursor follows it
        assert ids(audio.audio) == ["C", "B", "D"] and modal._list.highlighted == 2
        await pilot.press("K", "K", "K")
        assert ids(audio.audio) == ["B", "C", "D"] and modal._list.highlighted == 1
        await pilot.press("j", "D")  # remove Third (index 1 of the queue)
        assert ids(audio.audio) == ["B", "D"]
        await pilot.press("D")
        assert ids(audio.audio) == ["B"]
        await pilot.press("u")
        assert ids(audio.audio) == ["B", "D"]
        await pilot.press("u")
        assert ids(audio.audio) == ["B", "C", "D"] and modal._list.highlighted == 2
        await pilot.press("u")
        assert ids(audio.audio) == ["B", "C", "D"]


async def test_the_playing_track_cannot_be_moved_or_removed(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        modal = await open_queue(audio, pilot, B, C)
        shown = []
        with patch.object(modal, "notify", lambda msg, **kw: shown.append(msg)):
            await pilot.press("D", "J", "K")
            await pilot.press("enter")
        assert ids(audio.audio) == ["B", "C"] and audio.audio.entry is A
        assert shown[0].startswith("That track is playing") and shown[-1] == "Already playing."


async def test_enter_plays_the_highlighted_upcoming_track_now(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        modal = await open_queue(audio, pilot, B, C)
        with patch.object(audio.audio, "play_audio") as play:
            await pilot.press("j", "j", "enter")
        play.assert_called_once_with(C)
        assert ids(audio.audio) == ["B"] and audio.screen is modal


async def test_the_modal_follows_the_queue_while_open(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        modal = await open_queue(audio, pilot, B)
        await pilot.press("j")
        audio.audio._queue.append(C)
        audio.audio._queue_changed()
        await pilot.pause(0.2)
        assert titles(modal) == ["▶ Playing", "1. Second", "2. Third"] and modal._list.highlighted == 1
        audio.audio._queue.pop(0)  # the first upcoming track started elsewhere: the cursor keeps its row
        audio.audio._queue_changed()
        await pilot.pause(0.2)
        assert titles(modal) == ["▶ Playing", "1. Third"]
        audio.audio._entry, audio.audio._play_pending = None, False
        audio.audio._queue.clear()
        audio.audio._broadcast(lambda: __import__("src.tui.messages", fromlist=["x"]).PlayerStateUpdated(
            0.0, 0.0, False, playing=False))
        await pilot.pause(0.2)
        assert titles(modal) == ["Nothing queued. Press e on a video to add it."]


async def test_escape_closes_the_modal_and_q_works_again(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        modal = await open_queue(audio, pilot, B)
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert audio.screen is not modal
        await pilot.press("Q")
        await pilot.pause(0.2)
        assert isinstance(audio.screen, QueueModal)


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
        assert "--start=125" in built[0] and "Resuming at 2:05" in notices
        audio.config.set("resume_playback", False)
        built.clear()
        await asyncio.to_thread(controller._play_with_retries, A, 1, "mpv", "in.conf", "http://s", "")
        assert not any(a.startswith("--start") for a in built[0])
