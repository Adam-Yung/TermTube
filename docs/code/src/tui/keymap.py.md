# src/tui/keymap.py

The only place key bindings are written in code. `MainScreen` and `ChannelScreen` splice the lists into their `BINDINGS`
(`*keymap.LIST_NAV, *keymap.PLAYBACK, *keymap.ITEM_ACTIONS`), so the two screens cannot drift. The prose map, the design rules for
choosing keys, and the history of the first keymap are in `docs/features/keybindings.md`. The video
player's keys are in `src/tui/screens/watch_modal.py`, not here.

## Rules

- All bindings are `show=False`. The footer is the custom action bar (`src/tui/widgets/action_bar.py`).
- `SEARCH` and `GLOBAL` (`,` settings, `q` quit, `?` help) are shared by `MainScreen` and `ChannelScreen`, so the channel page answers them too. `MainScreen` puts `r` Refresh between `SEARCH` and `GLOBAL` to keep its footer order.
- Action names resolve to `action_<name>` on the screen: navigation to `ListNavMixin`, playback to `ItemActionsMixin` (which calls `app.audio`), item actions to the
  screen or its mixins. A binding whose action does not exist fails only when the key is pressed.
- Seek and percent bindings carry arguments in the action string (`audio_seek(-5)`, `audio_seek_pct(30)`).
- Textual names `[ ] { }` as `left_square_bracket`, `right_square_bracket`, `left_curly_bracket`, `right_curly_bracket`. The literal
  characters do not bind.
- `FOCUS_RECLAIM_KEYS` is not a binding. `ListNavMixin.on_key` uses it to move focus back to the list when one of these keys arrives
  while focus sits on the tab bar, because DOM changes can leave it there. Keep it in step with `LIST_NAV`.
- `FILTER` (`f`) is shared by both screens; `LIST_TOOLS` (`m`, `M`, `D`, `u`) is `MainScreen` only; `CHANNEL_PAGE` (`s` sort, `r` reload, `i` description) is `ChannelScreen` only and, unlike the rest, shows in the footer. `tests/unit/test_keymap.py` checks that every key here appears in the help screen and in `keybindings.md`.
- Adding a key also means the help screen, the action bar hints and the feature doc (`AGENTS.md`).
- `CHANNEL_PAGE` also holds the channel page's `B` (follow locally) and the playlist keys `P` `E` `S`; `SUBSCRIPTIONS` (`F`, the local Following list) is spliced into `MainScreen` only.
- `HISTORY_KEYS` (`Y` cycle the History source, `I` import YouTube rows into local history) is `MainScreen` only; both only hint outside the History tab / YouTube source.
