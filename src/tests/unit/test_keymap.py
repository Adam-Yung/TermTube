import re

import pytest

from src.tui import keymap
from src.tui.screens.channel_screen import ChannelScreen
from src.tui.screens.main_screen import MainScreen
from src.tui.screens.watch_modal import WatchModal


def _action_name(action: str) -> str:
    return re.split(r"[(\s]", action, maxsplit=1)[0].replace(".", "_")


@pytest.mark.parametrize("screen", [MainScreen, ChannelScreen, WatchModal])
def test_every_binding_has_an_action(screen):
    for binding in screen.BINDINGS:
        name = _action_name(binding.action)
        assert hasattr(screen, f"action_{name}"), f"{screen.__name__}: no action_{name} for key {binding.key}"


@pytest.mark.parametrize("screen", [MainScreen, ChannelScreen])
def test_no_key_bound_twice(screen):
    keys = [k for b in screen.BINDINGS for k in b.key.split(",")]
    assert len(keys) == len(set(keys)), sorted(k for k in set(keys) if keys.count(k) > 1)


def test_motion_keys_never_play_or_stop():
    by_key = {k: b.action for b in keymap.LIST_NAV + keymap.PLAYBACK for k in b.key.split(",")}
    assert by_key["h"] == "page_prev" and by_key["l"] == "page_next"
    assert by_key["a"] == "audio" and by_key["v"] == "watch" and by_key["x"] == "audio_stop"
