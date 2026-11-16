# src/tui/widgets/action_bar.py

The bottom-right box of the detail panel. It is either the shortcut grid (actions mode) or the now-playing bar (player mode: title, progress bar, time, key hints, queue hint). The audio host drives it; the widget holds no playback logic.

## Rules

- `set_player_mode` starts a buffering state: `dur == 0` draws an animated wave and a "Buffering… (Ns)" counter. The first `update_progress` with `dur > 0` stops the wave timer. "Buffering" that never ends means no `PlayerStateUpdated`/poll reached the bar, not a bug here (see `docs/features/architecture.md`, "Buffering stuck").
- `update_progress` ignores changes under 0.5 s position and 1 s duration while the pause state is unchanged. This keeps a paused or steady bar from re-rendering on every 0.5 s poll.
- `set_actions_mode` clears segments, queue length and the wave timer. Call it on every stop path or the next track inherits the old SponsorBlock overlay.
- `set_segments` overlays SponsorBlock ranges in green. The per-column map is cached by (width, duration) and rebuilt when either changes or segments are replaced.
- Theme colours come from `app.config.theme` and fall back to crimson when the app has no config (isolated widget tests). `THEME_COLORS` is shared with `video_list.py`. Call `refresh_theme` after a theme change; Rich markup is baked into the Static widgets.
- The key hints in `_update_np_keys` and the grid in `_get_actions_table` repeat `src/tui/keymap.py` by hand. Change them with the keymap (`docs/features/keybindings.md`).

## Limits

Height switches between 7 and 11 rows on mode change, so the thumbnail area above resizes and triggers `DetailPanel.RerenderRequested`.
