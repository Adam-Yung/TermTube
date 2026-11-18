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


_DISPLAY = {
    "left_square_bracket": "[", "right_square_bracket": "]", "left_curly_bracket": "{", "right_curly_bracket": "}",
    "comma": ",", "tab": "Tab", "space": "Space", "enter": "Enter", "left": "←", "right": "→",
}


def _keymap_keys() -> set[str]:
    lists = [keymap.LIST_NAV, keymap.PLAYBACK, keymap.ITEM_ACTIONS, keymap.LIST_TOOLS, keymap.GLOBAL,
             keymap.SEARCH_FILTERS, keymap.CHANNEL_PAGE, keymap.SUBSCRIPTIONS,
             keymap.PLAYLIST_TOOLS, keymap.HISTORY_KEYS,
             [keymap.SEARCH, keymap.FILTER, keymap.RAIL]]
    keys = {k for group in lists for b in group for k in b.key.split(",")}
    return {_DISPLAY.get(k, k) for k in keys}


def _expand_digit_range(tokens: set[str]) -> set[str]:
    return tokens | set("0123456789") if "0–9" in tokens else tokens


def _help_tokens() -> set[str]:
    from src.tui.screens.help_screen import _SECTIONS

    tokens = {t for _, rows in _SECTIONS for key, _ in rows for t in key.split()}
    return _expand_digit_range(tokens)


def _doc_tokens() -> set[str]:
    from pathlib import Path

    text = (Path(__file__).parents[3] / "docs" / "features" / "keybindings.md").read_text(encoding="utf-8")
    tokens = set(re.findall(r"`([^`\s]+)`", text))
    return _expand_digit_range(tokens | {"0–9"} if "`0`–`9`" in text else tokens)


def test_every_keymap_key_is_in_the_help_screen_and_the_keybindings_doc():
    keys = _keymap_keys()
    assert not keys - _help_tokens(), f"missing from help_screen.py: {sorted(keys - _help_tokens())}"
    assert not keys - _doc_tokens(), f"missing from keybindings.md: {sorted(keys - _doc_tokens())}"
