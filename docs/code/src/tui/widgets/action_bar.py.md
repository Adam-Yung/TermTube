# src/tui/widgets/action_bar.py

The bottom-right box of the detail panel. It is either the shortcut grid (actions mode) or the now-playing bar (player mode: title, progress bar, time, key hints, queue hint). The audio host drives it; the widget holds no playback logic.

## Rules

- `set_player_mode` starts a buffering state: `dur == 0` draws an animated wave and a "Buffering… (Ns)" counter. The first `update_progress` with `dur > 0` stops the wave timer. "Buffering" that never ends means no `PlayerStateUpdated`/poll reached the bar, not a bug here (see `docs/features/architecture.md`, "Buffering stuck").
- `update_progress` ignores changes under 0.5 s position and 1 s duration while the pause state is unchanged. This keeps a paused or steady bar from re-rendering on every 0.5 s poll.
- `set_actions_mode` clears segments, queue length and the wave timer. Call it on every stop path or the next track inherits the old SponsorBlock overlay.
- `set_segments` overlays SponsorBlock ranges in green. The drawing and its per-column cache are `SegmentBar` (`segment_bar.py`), shared with the video player.
- Theme colours come from `app.config.theme` and fall back to crimson when the app has no config (isolated widget tests). `THEME_COLORS` is shared with `video_rows.py` and other widgets. Call `refresh_theme` after a theme change; Rich markup is baked into the Static widgets.
- The grid (`_action_entries`) takes the row actions and their keys from `keymap.ROW_ACTIONS` / `keymap.key_of`, the tools from the screen's `HAS_*` flags. It never lists a key the Footer already shows (`/` search, `r` refresh, `,` settings, `?` help, `q` quit): `tests/tui/test_row_actions.py` fails if it does. The key hints in `_update_np_keys` still repeat the keymap by hand (`docs/features/keybindings.md`).
- `render_actions` picks the column count that fits the panel width (up to 5) and sets the panel height to the rows needed, at most 5 grid rows and what the detail panel can spare after `MIN_INFO_ROWS`. Entries that do not fit end in a `…` cell. It posts `HeightChanged` so the detail panel re-splits its height.

## Limits

Height is at least 7 in actions mode (more when the grid needs rows; the main screen lists every tool of every tab, 21 entries) and 11 in player mode, switching on mode change, so the thumbnail area above resizes and triggers `DetailPanel.RerenderRequested`.

## Prompt

`show_prompt(markup)` replaces the whole bar with one line until `clear_prompt()` (used by the remove question, `ListToolsMixin`). `_set_mode_actions` and `_set_mode_player` re-apply an open prompt, so a track change or a stop cannot hide a question that is still waiting for a key. The grid's entries come from `screen.panel_hints()` (`ItemActionsMixin`, extended by `MainScreen`): Enter and the row actions that apply to the highlighted row, then the tools that apply to the tab and focus (`keymap.PANEL_TOOLS`). The screen calls `render_actions` when the highlighted row, the rail cursor, the focus, the tab or the undo state changes.