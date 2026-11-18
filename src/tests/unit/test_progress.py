"""Resume point and watch time rules (src/progress.py) and the history fields they write."""

import pytest

from src import history, player, progress
from src.progress import ProgressTracker, resume_point, start_offset


class Cfg:
    def __init__(self, resume=True):
        self.resume_playback_enabled = resume
        self.history_enabled = True
        self.history_max = 500


@pytest.fixture
def hist(temp_history):
    return temp_history


def watched(vid="vid", **extra):
    history.add({"id": vid, "title": "T", "uploader": "U", "duration": 600, **extra}, Cfg())


@pytest.mark.parametrize(("pos", "dur", "want"), [
    (9.9, 600, None), (10, 600, 10), (300.7, 600, 300), (569, 600, 569), (570, 600, None), (599, 600, None),
    (50, 0, None), (50, -1, None),
])
def test_resume_point_rules(pos, dur, want):
    assert resume_point(pos, dur) == want


def test_start_offset_reads_the_saved_point(hist):
    watched()
    history.record_progress("vid", resume_s=120, watched=0)
    assert start_offset({"id": "vid"}, Cfg()) == 120


def test_start_offset_is_none_when_off_live_unknown_or_too_early_or_near_the_end(hist):
    watched()
    history.record_progress("vid", resume_s=120, watched=0)
    assert start_offset({"id": "vid"}, Cfg(resume=False)) is None
    assert start_offset({"id": "vid", "is_live": True}, Cfg()) is None
    assert start_offset({"id": "vid", "live_status": "is_live"}, Cfg()) is None
    assert start_offset({"id": "other"}, Cfg()) is None
    assert start_offset({}, Cfg()) is None
    history.record_progress("vid", resume_s=5, watched=0)
    assert start_offset({"id": "vid"}, Cfg()) is None
    history.record_progress("vid", resume_s=590, watched=0)
    assert start_offset({"id": "vid"}, Cfg()) is None


def test_record_progress_adds_time_sets_the_point_and_fills_a_missing_duration(hist):
    history.add({"id": "vid", "title": "T"}, Cfg())
    history.record_progress("vid", resume_s=50, watched=12.34, duration=300.2)
    history.record_progress("vid", resume_s=80, watched=5, duration=999)
    record = history.get("vid")
    assert record["resume_s"] == 80 and record["seconds"] == 17.3 and record["duration"] == 300


def test_record_progress_ignores_a_video_without_a_record(hist):
    history.record_progress("ghost", resume_s=50, watched=5)
    assert history.get("ghost") is None and history.all_entries() == []


def test_playing_again_keeps_time_point_and_duration(hist):
    watched()
    history.record_progress("vid", resume_s=70, watched=30)
    history.add({"id": "vid", "title": "T"}, Cfg())
    record = history.get("vid")
    assert (record["plays"], record["seconds"], record["resume_s"], record["duration"]) == (2, 30, 70, 600)


def test_ordered_sorts_by_plays_or_time_and_keeps_newest_first_on_ties(hist):
    rows = [
        {"id": "a", "plays": 1, "seconds": 500},
        {"id": "b", "plays": 3, "seconds": 10},
        {"id": "c", "plays": 3, "seconds": 10},
        {"id": "d", "plays": 3, "seconds": 90},
    ]
    assert [e["id"] for e in history.ordered(rows, "plays")] == ["d", "b", "c", "a"]
    assert [e["id"] for e in history.ordered(rows, "time")] == ["a", "d", "b", "c"]
    assert history.ordered(rows, "recent") is rows


class Spy:
    def __init__(self, monkeypatch):
        self.calls = []
        monkeypatch.setattr(history, "record_progress", lambda vid, **kw: self.calls.append((vid, kw)))


def test_tracker_writes_every_five_seconds_of_watched_time_not_of_polls(monkeypatch):
    spy = Spy(monkeypatch)
    tracker = ProgressTracker({"id": "vid"})
    for n in range(0, 21):  # 0, 0.5, ... 10 s in half-second polls
        tracker.tick(n * 0.5, 600)
    assert [round(kw["watched"], 1) for _, kw in spy.calls] == [5.0, 5.0]
    assert [kw["resume_s"] for _, kw in spy.calls] == [None, 10]  # the 5 s write is below the 10 s floor
    tracker.tick(10.5, 600)
    tracker.finish()
    assert [round(kw["watched"], 1) for _, kw in spy.calls][-1] == 0.5 and spy.calls[-1][1]["resume_s"] == 10


def test_tracker_ignores_seeks_pauses_and_jumps(monkeypatch):
    spy = Spy(monkeypatch)
    tracker = ProgressTracker({"id": "vid"})
    for pos in (100, 100, 100, 160, 161, 40, 41, 41):  # pause, forward seek of 59 s, back seek
        tracker.tick(pos, 600)
    tracker.finish()
    assert len(spy.calls) == 1 and round(spy.calls[0][1]["watched"], 1) == 2.0


def test_finish_writes_the_last_position_once(monkeypatch):
    spy = Spy(monkeypatch)
    tracker = ProgressTracker({"id": "vid"})
    tracker.tick(200, 600)
    tracker.tick(200.5, 600)
    tracker.finish()
    tracker.finish()
    assert len(spy.calls) == 1 and spy.calls[0][1]["resume_s"] == 200


def test_finish_with_completed_clears_the_point(monkeypatch):
    spy = Spy(monkeypatch)
    tracker = ProgressTracker({"id": "vid"})
    tracker.tick(300, 600)
    tracker.finish(completed=True)
    assert spy.calls[0][1]["resume_s"] is None


def test_stopping_past_ninety_five_percent_clears_the_point(monkeypatch):
    spy = Spy(monkeypatch)
    tracker = ProgressTracker({"id": "vid"})
    tracker.tick(580, 600)
    tracker.finish()
    assert spy.calls[0][1]["resume_s"] is None


@pytest.mark.parametrize("entry", [{"id": "v", "is_live": True}, {"id": "v", "live_status": "is_live"}, {}])
def test_live_and_idless_entries_record_nothing(monkeypatch, entry):
    spy = Spy(monkeypatch)
    tracker = ProgressTracker(entry)
    for n in range(40):
        tracker.tick(n, 600)
    tracker.finish()
    assert spy.calls == []


def test_a_tracker_that_never_polled_writes_nothing(monkeypatch):
    spy = Spy(monkeypatch)
    ProgressTracker({"id": "vid"}).finish()
    assert spy.calls == [] and progress.MIN_RESUME_S == 10


def test_start_args_is_the_one_place_for_the_flag():
    assert player.start_args(754.9) == ["--start=754"] and player.start_args(None) == [] and player.start_args(0) == []
    cmd = player.audio_command("mpv", input_conf="i", socket_path="s", stream_url="u", start=95)
    assert "--start=95" in cmd and cmd.index("--start=95") < cmd.index("--")


def test_the_video_player_builds_start_from_the_same_helper():
    from src.tui.screens.watch_modal import WatchModal

    modal = WatchModal({"id": "v", "title": "T"})
    with_start = modal._build_command("mpv", "in", "T", ["http://u"], "page", "bv+ba/b", [], 754)
    without = modal._build_command("mpv", "in", "T", ["http://u"], "page", "bv+ba/b", [])
    assert "--start=754" in with_start and with_start.index("--start=754") < with_start.index("--")
    assert not any(a.startswith("--start") for a in without)
