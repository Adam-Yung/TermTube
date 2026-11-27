"""AudioController: state lives on the app, screens mirror it through messages."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from textual.screen import Screen

from src.tui.audio_controller import AudioController, _socket_for

ENTRY = {"id": "AAAAAAAAAAA", "title": "First"}
OTHER = {"id": "BBBBBBBBBBB", "title": "Second"}


class Recorder(Screen):
    """A screen with no widgets that records the audio messages it receives."""

    def __init__(self):
        super().__init__()
        self.seen = []

    def on_player_state_updated(self, message):
        self.seen.append(("progress", message.pos, message.playing))

    def on_audio_track_changed(self, message):
        self.seen.append(("track", message.entry["id"]))

    def on_audio_queue_changed(self, message):
        self.seen.append(("queue", message.queue_len))


@pytest.fixture
def audio(app, mock_mpv_ipc, tmp_path, monkeypatch):
    monkeypatch.setattr("src.history.HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(AudioController, "_launch_worker", lambda *a, **k: None)
    monkeypatch.setattr("src.tui.audio_controller.cleanup_ipc", lambda path: None)
    return app


def fake_proc():
    proc = MagicMock()
    proc.poll.return_value = None
    return proc


async def test_every_screen_receives_progress_while_screens_are_pushed(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        controller = audio.audio
        controller.play_audio(ENTRY)
        controller._proc = fake_proc()
        covering = Recorder()
        await audio.push_screen(covering)
        await asyncio.to_thread(controller.poll_once, controller._session)
        await pilot.pause(0.2)
        assert ("progress", 10.0, True) in covering.seen
        main = audio.screen_stack[1]
        assert main.query_one("#detail-panel").action_bar._pos == 10.0
        audio.pop_screen()
        await pilot.pause(0.1)
        assert controller.is_playing and controller.progress == (10.0, 300.0, False)


async def test_play_stops_old_track_on_its_own_socket_before_the_session_moves(audio, mock_mpv_ipc):
    send, _ = mock_mpv_ipc
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        controller.play_audio(ENTRY)
        first_session = controller._session
        controller._proc = fake_proc()
        controller.play_audio(OTHER)
        quits = [c for c in send.call_args_list if c.args[0] == {"command": ["quit"]}]
        assert [c.kwargs["socket_path"] for c in quits] == [_socket_for(first_session)]
        assert controller._session == first_session + 1 and controller.entry is OTHER
        assert _socket_for(controller._session) != _socket_for(first_session)


async def test_stop_broadcasts_and_clears_queue(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        controller = audio.audio
        recorder = Recorder()
        await audio.push_screen(recorder)
        controller.play_audio(ENTRY)
        controller.enqueue_audio(OTHER)
        await pilot.pause(0.1)
        assert ("track", "AAAAAAAAAAA") in recorder.seen and ("queue", 1) in recorder.seen
        controller.stop_audio()
        await pilot.pause(0.1)
        assert ("progress", 0.0, False) in recorder.seen
        assert not controller.is_playing and controller.queue == ()


async def test_enqueue_skip_and_can_enqueue(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        assert not controller.can_enqueue(OTHER)
        controller.enqueue_audio(ENTRY)
        assert controller.entry is ENTRY
        assert controller.can_enqueue(OTHER) and not controller.can_enqueue(ENTRY)
        controller.enqueue_audio(OTHER)
        controller.enqueue_audio(OTHER)
        assert controller.queue == (OTHER,) and not controller.can_enqueue(OTHER)
        controller.skip_audio()
        assert controller.entry is OTHER and controller.queue == ()


async def test_a_stale_launch_failure_does_not_stop_the_newer_track(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        controller.play_audio(ENTRY)
        old_session = controller._session
        controller._proc = fake_proc()
        controller.play_audio(OTHER)
        controller._stop_if_current(old_session)
        assert controller.is_playing and controller.entry is OTHER


async def test_history_is_recorded_once_on_the_first_successful_poll(audio):
    async with audio.run_test(size=(100, 30)) as pilot:
        controller = audio.audio
        controller.play_audio(ENTRY)
        controller._proc = fake_proc()
        with patch("src.history.add") as add:
            for _ in range(3):
                await asyncio.to_thread(controller.poll_once, controller._session)
            await pilot.pause(0.1)
        assert add.call_count == 1
        assert add.call_args.args[0] == ENTRY


THIRD = {"id": "CCCCCCCCCCC", "title": "Third"}


async def test_previous_returns_through_the_tracks_already_played(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        controller.play_many([ENTRY, OTHER, THIRD])
        assert not controller.has_previous
        controller.skip_audio()
        controller.skip_audio()
        controller.previous_audio()
        assert controller.entry is OTHER and controller.queue == (THIRD,)
        controller.previous_audio()
        assert controller.entry is ENTRY and controller.queue == (OTHER, THIRD)
        controller.previous_audio()
        assert controller.entry is ENTRY and not controller.has_previous


async def test_a_finished_track_is_the_previous_one(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        controller.play_many([ENTRY, OTHER])
        controller._on_finished(ENTRY, controller._session)
        controller.previous_audio()
        assert controller.entry is ENTRY and controller.queue == (OTHER,)


async def test_stop_and_a_new_playlist_forget_the_played_tracks(audio):
    async with audio.run_test(size=(100, 30)):
        controller = audio.audio
        controller.play_many([ENTRY, OTHER])
        controller.skip_audio()
        controller.play_many([THIRD, ENTRY])
        assert not controller.has_previous
        controller.skip_audio()
        controller.stop_audio()
        controller.play_audio(OTHER)
        assert not controller.has_previous


async def test_the_less_than_key_plays_the_previous_track(audio):
    async with audio.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        controller = audio.audio
        controller.play_many([ENTRY, OTHER])
        controller.skip_audio()
        controller._proc = fake_proc()
        await pilot.press("<")
        assert controller.entry is ENTRY
