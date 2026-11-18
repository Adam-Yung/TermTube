# src/tui/screens/main_screen.py

The root screen: header, tab bar, `VideoListPanel`, `DetailPanel`, debug log. It is thin; behaviour lives in the mixins, in MRO order `PlaylistToolsMixin`, `LibraryRailMixin`, `ListToolsMixin`, `ListNavMixin`, `DetailFocusMixin`, `ItemActionsMixin`, `AudioBarMixin`, `FeedLoaderMixin`, `DebugLogMixin` (wiring map: `docs/features/architecture.md`). The screen itself owns tabs, search, subscription rows, the header spinner counter, and quit.

## Tabs

- `_current_tab` is the view shown: a tab id, `search`, or on the Library tab a collection (`library`, `library:video`, `library:audio`, `playlist:<id>`). `tab_of(view)` maps a view to its tab (every Library collection is `library`); the tab bar, `H`/`L` cycling and the Help restore all go through it. Leaving and re-entering Library reopens `_library_view`.
- `on_tabs_tab_activated` ignores an activation of the current tab (compared through `tab_of`). Appending list items can move focus to the tab bar, which re-fires activation of the tab already shown and would reload it. A real switch always changes the id.
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

`_prewarm_cookies` (after first refresh) calls `cookies.prewarm`; `_refresh_account(feed_key)` (the empty-feed dialog's "refresh" choice) invalidates the jar, clears the feed's cached ids and reloads. `_maybe_show_image_warning` runs once after the first refresh: no pixel-image support and the warning not dismissed. `_prompt_ytdlp_update`/`_show_empty_feed_modal` are called by `FeedLoaderMixin` from worker threads through `call_from_thread`.

## List tools

`ListToolsMixin` comes first in the MRO so its `on_key` can swallow keys while a remove question is open. `_removals()` is the per-view table of remove handlers (History, the three Library collections, playlists). `action_nav_back` clears a kept filter first, then on Library moves focus from the list to the rail, then on Search pops the previous query.
- `_search` is a `SearchStack`. `_show_search_results` saves the page and row of the results being left (`_save_search_position`, also when switching tabs), pushes the query and shows it through `_show_search_frame`. `action_nav_back` pops it only on the Search tab. The saved position is applied once by `FeedLoaderMixin._finish_search_load` after the (cached) results load.

- `s` / `t` (`action_search_sort`, `action_search_type`) open the shared `SortModal` with the search sort or type options and write the choice to the current `SearchFrame` (`set_filter`), then `_show_search_frame` reloads (own cache entry per sort and type). Off the Search tab they only hint. Enter on a playlist row of a Search result hints "Press b to open the playlist in the browser" (`b` opens the page); channel rows open the channel page as on Subscriptions.

`_removals()` registers History, Library (`library_delete.removal(config, kind)` for each collection) and `PlaylistToolsMixin._playlist_removals()`.

## Library rail

`#library-rail` (`LibraryRail`) sits left of the list and is shown only on the Library tab (`_show_rail`); behaviour is in `LibraryRailMixin`. `_selected_entry` returns None while the rail has focus, so row actions never act on a row the user is not on. `Tab` is `keymap.RAIL`.

## History sort

`s` is `search_sort`: on the Search tab it picks a result order, on the local History tab (`_current_tab == "history"`, not the YouTube lists) it opens `SortModal` with `_HISTORY_SORTS` (recent, most watched, longest watched), elsewhere it is a hint. The choice lives in `_history_sort` for the session and is applied where the view loads (`FeedLoaderMixin._stream_view`): `recent` keeps the day headers, the other two drop them because the order no longer follows time. The History `Removal.reload` applies the same order, so removing or undoing a row does not reshuffle a sorted list. `action_quit_app` calls `history.flush()` after stopping audio: the force-exit timer ends in `os._exit`, which skips `atexit`.

`_crumbs()` returns the current tab's label without its emoji (a playlist drill-down counts as Playlists); a channel page opened from here starts its breadcrumb with it.

**Following (local).** `F` on the Subscriptions tab (`action_following`, `keymap.SUBSCRIPTIONS`) opens the locally followed channels as a drill-down like a playlist: the tab goes on `_nav_stack`, `_current_tab` becomes `following`, and `FeedLoaderMixin._load_following` fills the list from `channel_bookmarks`. Enter opens the channel as on Subscriptions. Elsewhere `F` says to open Subscriptions first.

`action_nav_back` reloads the view it returns to when that tab is already the active one. Setting an unchanged `Tabs.active` fires no event, so before this fix Backspace out of a playlist (and out of Following) left the drill-down's rows on screen.
