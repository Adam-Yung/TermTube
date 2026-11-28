# `src/tui/screens/help_screen.py`

The keyboard reference modal (`?`, F7, the Help tab). Content is data: `_SECTIONS` is a list of `(title, [(keys, description)])`,
rendered by `_render_help` with the theme colour. It must match `src/tui/keymap.py` and `docs/features/keybindings.md`; `tests/unit/test_keymap.py` fails when a
keymap key is missing from `_SECTIONS` or from the doc, so a key change touches all three in the same commit.

The text is Rich markup. Literal brackets in key names (`[ / ]`) are safe only because a space follows `[`; do not write `[x]` forms.

The box is `#help-outer` in `theme.tcss` (90% high, 80% wide up to 100); the text scrolls inside `#help-scroll`.
Theme colours are duplicated from the action bar's table; `ActionBar.THEME_COLORS` is the source if it needs unifying.
