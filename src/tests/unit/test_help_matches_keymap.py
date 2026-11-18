"""Every key the Actions panel or the Enter menu shows is in the help screen, and the F-keys match the tabs."""

import re

from src.tui import keymap
from src.tui.screens.help_screen import _SECTIONS
from src.tui.screens.main_screen import _TABS, MainScreen


def _help_tokens() -> set[str]:
    text = " ".join(key for _, rows in _SECTIONS for key, _ in rows)
    return set(re.split(r"[\s/,]+", text))


def test_every_panel_and_menu_key_is_in_the_help_screen():
    tokens = _help_tokens()
    actions = [row.action for row in keymap.ROW_ACTIONS] + [a for tool in keymap.PANEL_TOOLS for a in tool.actions]
    missing = {a: keymap.key_of(a) for a in actions if keymap.key_of(a) not in tokens}
    assert not missing


def test_the_footer_keys_are_in_the_help_screen():
    rows = {key for _, section in _SECTIONS for key, _ in section}
    assert {"/", "?", ","} <= rows and "q" in _help_tokens()


def test_f_keys_match_the_tabs():
    bound = {b.key for b in MainScreen.BINDINGS if b.key.startswith("f") and b.key[1:].isdigit()}
    assert bound == {f"f{n}" for n in range(1, len(_TABS) + 1)}
    assert any("F1–F6" in key for _, rows in _SECTIONS for key, _ in rows)
