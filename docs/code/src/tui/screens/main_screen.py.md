# src/tui/screens/main_screen.py

The root screen: header, tab bar, `VideoListPanel`, `DetailPanel`, debug log. It is thin; behaviour lives in the mixins, in MRO order `ListToolsMixin`, `ListNavMixin`, `DetailFocusMixin`, `ItemActionsMixin`, `AudioBarMixin`, `FeedLoaderMixin`, `DebugLogMixin` (wiring map: `docs/features/architecture.md`). The screen itself owns tabs, search, the playlist drill-down, subscription rows, the header spinner counter, and quit.

## Tabs

- `_current_tab` is a tab id, or `playlist:<name>` inside a playlist, or `search`. `_nav_stack` holds the tab to return to (Backspace/Esc) after a playlist drill-down.
- `on_tabs_tab_activated` ignores an activation of the current tab. Appending list items can move focus to the tab bar, which re-fires activation of the tab already shown and would reload it. A real switch always changes the id.
- Search and Help are tabs that open a modal. Cancelling the search modal must not set `tabs.active` (that re-activates the current tab and reloads its list); `_opening_search_tab` suppresses the dialog when `_show_search_results` sets the tab itself.
- Switching away from the home tab saves the feed stash first (`FeedLoaderMixin._save_feed_stash`); `on_unmount` and quit do the same.

## Subscriptions rows

The Subscriptions list holds channels, not videos. `on_video_list_panel_selected` routes them to `_focus_channel`: paint the channel into the detail panel, then `_avatar_worker` (group `ch_thumb`) loads the avatar from the entry's thumbnail URL, and `_channel_info_worker` (group `ch_focus`) fetches full channel info when the entry lacks a description or a thumbnail URL. `_apply_channel_info` merges the result if the cursor is still on that channel and restarts the avatar with the better URL.

The avatar renders into the shared detail panel, so a cursor move must cancel it: `_cancel_pending_focus_and_thumb` is overridden to also bump `_avatar_session`. Both avatar launches bump the counter and pass the new value to the worker.

## Header spinner

`_worker_start`/`_worker_end` keep `_active_workers` under a lock (called from worker threads) and drive `AppHeader`. The spinner shows while any counted worker runs. Only feed, channel-info and metadata workers are counted.

## Quit

`action_quit_app` saves the stash, stops audio (`app.audio.stop_audio()`), schedules `_force_exit` on a 2 s daemon timer and calls `app.exit()`. `_force_exit` kills registered subprocesses and calls `os._exit(0)` if Textual's shutdown hangs (a blocked worker thread would otherwise keep the process alive). Tests must patch `_force_exit`, or the runner dies.

## Startup prompts

`_maybe_show_image_warning` runs once after the first refresh: no pixel-image support and the warning not dismissed. `_prompt_ytdlp_update`/`_show_empty_feed_modal` are called by `FeedLoaderMixin` from worker threads through `call_from_thread`.

## List tools

`ListToolsMixin` comes first in the MRO so its `on_key` can swallow keys while a remove question is open. `_removals()` is the per-tab table of remove handlers (History only). `action_nav_back` clears a kept filter before it pops `_nav_stack`.
- `_search` is a `SearchStack`. `_show_search_results` saves the page and row of the results being left (`_save_search_position`, also when switching tabs), pushes the query and shows it through `_show_search_frame`. `action_nav_back` pops it only when `_nav_stack` is empty and the Search tab is current, so playlist and channel "back" keep priority. The saved position is applied once by `FeedLoaderMixin._finish_search_load` after the (cached) results load.

- `s` / `t` (`action_search_sort`, `action_search_type`) open the shared `SortModal` with the search sort or type options and write the choice to the current `SearchFrame` (`set_filter`), then `_show_search_frame` reloads (own cache entry per sort and type). Off the Search tab they only hint. Enter on a playlist row of a Search result hints "Press b to open the playlist in the browser" (`b` opens the page); channel rows open the channel page as on Subscriptions.
