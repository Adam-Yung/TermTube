# The screen: lists, detail panel, actions, themes

> Verified: 2026-11-28 · Sources: `src/tui/screens/main_screen.py`, `src/tui/screens/mixins/list_nav.py`, `src/tui/screens/mixins/detail_focus.py`, `src/tui/screens/mixins/item_actions.py`, `src/tui/widgets/video_list.py`, `src/tui/widgets/action_bar.py`, `src/tui/theme.tcss`, `src/tui/layout.py`
> Serves: `ui`
> Owns: `src/tui/fmt.py`, `src/tui/layout.py`, `src/tui/views.py`, `src/tui/theme.tcss`, `src/tui/screens/__init__.py`, `src/tui/screens/main_screen.py`, `src/tui/screens/nav_modal.py`, `src/tui/screens/mixins/__init__.py`, `src/tui/screens/mixins/app_pages.py`, `src/tui/screens/mixins/debug_log.py`, `src/tui/screens/mixins/detail_focus.py`, `src/tui/screens/mixins/item_actions.py`, `src/tui/screens/mixins/list_nav.py`, `src/tui/widgets/__init__.py`, `src/tui/widgets/action_bar.py`, `src/tui/widgets/app_header.py`, `src/tui/widgets/detail_panel.py`, `src/tui/widgets/page_indicator.py`, `src/tui/widgets/video_*.py`, `src/tui/widgets/row_markup.py`, `src/tui/widgets/list_*.py`

## What it does

A header and tab bar, a paged list, and a detail panel (thumbnail, text, then the Actions grid or the audio bar). Library, History and
Subscriptions add a left side list. `Enter` opens an action menu, the backtick key a page picker, `Ctrl+D` the debug log. Four themes.

## How it works

`MainScreen` composes the widgets and takes its behaviour from mixins ([architecture.md](architecture.md)). `VideoListPanel` holds pages,
filter, marks and footer and never fetches. Moving the cursor paints basic fields at once, then loads details and the thumbnail in workers.
`ActionBar` shows what the screen's `panel_hints()` says applies. `layout.py` and `theme.tcss` set the widths and the narrow layout.

## Code

`src/tui/screens/main_screen.py`, `src/tui/screens/mixins/list_nav.py`, `src/tui/screens/mixins/detail_focus.py`, `src/tui/screens/mixins/item_actions.py`,
`src/tui/widgets/video_list.py`, `src/tui/widgets/row_markup.py`, `src/tui/widgets/action_bar.py`, `src/tui/widgets/detail_panel.py`, `src/tui/theme.tcss`. Mirrors under `docs/code/`;
decisions in `docs/decisions/ui.md`.

## Rules that must hold

- The UI thread never blocks on the network or on large file work.
- Text from outside (titles, errors) is escaped before it is parsed as markup.
- A key that cannot act says why. Keys are defined in `src/tui/keymap.py` only ([keybindings.md](keybindings.md)).

## Limits

- At 80x24 the Actions panel fits about 8 entries; entries that do not fit end in a `…` cell.
- The look in Windows Terminal is not checked.

## How to check it

`src/tests/tui/test_layout_audit.py`, `src/tests/tui/test_screen_layout_audit.py`, `src/tests/tui/test_row_actions.py`, `src/tests/tui/test_markup_escaping.py`, `src/tests/unit/test_theme_wiring.py`.
