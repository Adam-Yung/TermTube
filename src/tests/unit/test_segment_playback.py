"""The SponsorBlock parts both players share: the coloured progress bar and the video player's skip."""

from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from src.sponsorblock import Segment
from src.strings import text
from src.tui.screens.watch_modal import WatchModal
from src.tui.widgets.action_bar import ActionBar

SEGMENTS = [Segment(20.0, 40.0, "sponsor"), Segment(70.0, 90.0, "intro")]
# 10 columns over 100 s with the position at 50 s: columns 2-3 and 7-8 are inside a segment.
BAR = (
    "[#6666ff]██[/#6666ff][#22c55e]██[/#22c55e][#6666ff]█[/#6666ff]"
    "[#2a2a40]░░[/#2a2a40][#166534]░░[/#166534][#2a2a40]░[/#2a2a40]"
)
PLAIN = "[#6666ff]█████[/#6666ff][#2a2a40]░░░░░[/#2a2a40]"


def modal():
    return WatchModal({"id": "v", "title": "T"})


def test_the_video_bar_colours_segment_columns_and_follows_new_segments():
    player = modal()
    assert player._render_bar(50.0, 100.0, 10) == PLAIN
    assert player._render_bar(50.0, 0.0, 10) == "[#2a2a40]──────────[/#2a2a40]"
    player._set_segments(SEGMENTS)
    assert player._render_bar(50.0, 100.0, 10) == BAR
    player._set_segments(SEGMENTS[1:])
    assert player._render_bar(50.0, 100.0, 10) == (
        "[#6666ff]█████[/#6666ff][#2a2a40]░░[/#2a2a40][#166534]░░[/#166534][#2a2a40]░[/#2a2a40]"
    )


def test_the_action_bar_draws_the_same_segment_columns():
    bar = ActionBar()
    assert bar._text_bar(50.0, 100.0, 10) == PLAIN
    bar.set_segments(SEGMENTS)
    assert bar._text_bar(50.0, 100.0, 10) == BAR


def test_the_video_player_skips_each_segment_once():
    player = modal()
    player._set_segments(SEGMENTS)
    player._ipc = MagicMock()
    player.notify = MagicMock()
    app = SimpleNamespace(config=SimpleNamespace(sponsorblock_auto_skip=True), call_from_thread=MagicMock())
    positions = iter([(25.0, 100.0, False), (26.0, 100.0, False), (75.0, 100.0, False)])
    with patch.object(WatchModal, "app", new_callable=PropertyMock, return_value=app), patch(
        "src.player.poll_audio_properties", lambda **_: next(positions)
    ):
        for _ in range(3):
            WatchModal._poll_mpv_threaded.__wrapped__(player)
    assert [c.args[0] for c in player._ipc.call_args_list] == [["seek", 40.0, "absolute"], ["seek", 90.0, "absolute"]]
    skipped = [c.args[1] for c in app.call_from_thread.call_args_list if c.args[0] is player.notify]
    assert skipped == [
        text("watch_modal.skipped", category="sponsor", seconds=20),
        text("watch_modal.skipped", category="intro", seconds=20),
    ]
