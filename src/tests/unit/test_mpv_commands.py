"""The mpv command lines: what a local file, a stream and the terminal flags look like."""

from types import SimpleNamespace

from src import player
from src.tui.screens.watch_modal import WatchModal


def audio(**kwargs):
    return player.audio_command("mpv", input_conf="i.conf", socket_path="sock", **kwargs)


def test_audio_command_keeps_mpv_off_the_tui_terminal_but_lets_errors_through():
    cmd = audio(stream_url="https://cdn/x")
    assert "--no-input-terminal" in cmd and "--no-terminal" not in cmd
    assert "--msg-level=all=error" in cmd


def test_a_direct_url_or_file_uses_no_ytdl_and_no_format():
    cmd = audio(stream_url="C:\\music\\tone.wav")
    assert "--no-ytdl" in cmd and not any(c.startswith("--ytdl-format") for c in cmd)
    assert cmd[-2:] == ["--", "C:\\music\\tone.wav"]


def test_a_page_url_still_asks_mpv_to_resolve_it():
    cmd = audio(page_url="https://www.youtube.com/watch?v=AAAAAAAAAAA", ytdl_format="ba/b")
    assert "--ytdl-format=ba/b" in cmd and "--no-ytdl" not in cmd


def test_the_video_player_plays_a_local_file_directly():
    host = SimpleNamespace(_socket="sock")
    cmd = WatchModal._build_command(host, "mpv", "i.conf", "t", ["/videos/a.mp4"], "/videos/a.mp4", "bv+ba/b", [])
    assert "--no-ytdl" in cmd and cmd[-2:] == ["--", "/videos/a.mp4"]
    assert not any(c.startswith("--ytdl-format") for c in cmd)
