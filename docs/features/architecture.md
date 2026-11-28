# Architecture: the wiring map

> Verified: 2026-11-28 · Sources: `src/tui/app.py`, `src/main.py`, `src/tui/screens/main_screen.py`, `src/tui/messages.py`
> Serves: `ui`, `quality`
> Owns: `src/__init__.py`, `src/main.py`, `src/entries.py`, `src/store.py`, `src/strings.py`, `src/strings.json`, `src/tui/__init__.py`, `src/tui/app.py`, `src/tui/messages.py`, `src/ui/__init__.py`

## What it does

How the pieces connect. For why a file is written the way it is, read its mirror in `docs/code/`. For settled calls, `docs/decisions/`.

## Layers

| Layer | File | Role |
|---|---|---|
| Entry | `src/main.py` (dependency check in `src/deps.py`) | CLI args, logger, imports `textual_image` before Textual, launches the app |
| App | `src/tui/app.py` | `TermTubeApp`: config and cache, screen push, housekeeping, warm-ups |
| Screens | `src/tui/screens/main_screen.py`, `channel_screen.py`, `queue_screen.py` | Compose widgets and mixins; dialogs are the other files in `src/tui/screens/` |
| Mixins | `src/tui/screens/mixins/` | list navigation and tools, playlist tools and rows, Library rail, detail focus, item actions, feed loading, paging and list sources, search tab, subscription rows, feed dialogs, channel header, content and playlist, Help/Settings pages, audio bar, debug log |
| Audio | `src/tui/audio_controller.py` (state, polling, completion), `audio_launch.py` (launch thread), `audio_queue.py` (queue), `segment_skip.py` | `app.audio`: mpv process, queue, polling, SponsorBlock skip |
| Widgets | `src/tui/widgets/` | list (`video_list.py` with `list_cursor.py`, `list_filter.py`, `list_footer.py`, `video_rows.py`, `row_markup.py`), detail panel, action bar, segment bar, thumbnail, page indicator, header, channel info, Library rail |
| Keys | `src/tui/keymap.py` | The keymap of the main, channel and queue pages (`docs/features/keybindings.md`) |
| Views and URLs | `src/tui/views.py`, `src/tui/urls.py`, `src/tui/screens/channel_tabs.py` | view ids and their tabs; YouTube page URLs; channel tab ids |
| Messages | `src/tui/messages.py` | `PlayerStateUpdated`, `AudioTrackChanged`, `AudioQueueChanged`, `AudioSegmentsLoaded`: the audio controller broadcasts them to every screen on the stack |
| Thumbnails | `src/tui/thumb_loader.py`, `src/ui/thumbnail.py`, `src/thumbnail_http.py` | worker-side loading; validate and half-block render; the HTTP fetch and its TLS contexts |
| yt-dlp | `src/ytdlp.py` (opts, feeds, search, channels), `src/flat_entries.py` (flat rows), `src/feed_cache.py` (cached id lists), `src/feed_cursor.py`, `src/cookies.py`, `src/downloads.py`, `src/streams.py` | all extraction; `streams.py` resolves and caches playback URLs |
| InnerTube | `src/innertube.py` (requests), `src/innertube_pages.py` (replies), `src/innertube_rows.py` (list items) | search, video details, channels, playlists and Mixes without yt-dlp |
| Playlists (remote) | `src/playlist_fetch.py` | reads a playlist or Mix for the playlist page and for playing from a row |
| Player | `src/player.py` (mpv commands, launch and retry), `src/mpv_ipc.py` (socket or pipe transport) | |
| Row types | `src/entries.py` | `TypedDict`s for video, channel, playlist and library rows (annotations only) |
| Data | `src/cache.py`, `src/history.py`, `src/library.py` (index, delete) with `src/library_scan.py` (folder walk), `src/playlist.py`, `src/search_history.py`, `src/channel_bookmarks.py`, `src/config.py` | disk and RAM state |
| Store | `src/store.py` | locked, atomic, versioned JSON file shared by history, playlists, search history and the Library index; a corrupt file is kept as `.bad` and the store starts empty |
| Errors | `src/errors.py` | typed `SourceError` (`SignInRequired`, `RateLimited`, `NetworkDown`, `ExtractionFailed`) from `classify(exc)`; loaders show its message |
| Search | `src/search_stack.py`, `src/fuzzy.py`, `src/library_query.py` | session stack of searches (Backspace), list-filter ranking, Library `key:value` queries |
| Progress | `src/progress.py` | turns mpv's polled position into history `resume_s` and `seconds` |
| Settings | `src/tui/settings_fields.py` | the Settings rows: names, parsing, validation (`SettingsModal` renders them) |
| Platform | `src/plat.py` | paths, clipboard, process registry, IPC paths |
| Install | `src/bootstrap.py`, `src/release_download.py`, `src/updater.py` | managed tools and updates ([install.md](install.md)) |

## Screens and mixins

```
MainScreen (PlaylistTools, LibraryRail, ListTools, ListNav, DetailFocus, ItemActions, AudioBar, FeedLoader, DebugLog,
            SearchTab, SubscriptionRows, FeedPrompts, AppPages)
 |- AppHeader, Tabs, LibraryRail, VideoListPanel, DetailPanel (ThumbnailWidget + ActionBar), RichLog
 |- pushes: ChannelScreen, WatchModal, DownloadModal, SearchModal, SettingsModal, QueueScreen, PlaylistModal, HelpScreen, ...
ChannelScreen (ChannelPlaylist, ListNav, DetailFocus, ItemActions, AudioBar, ChannelHeader, ChannelContent, AppPages)
 |- ChannelInfoPanel, Tabs, VideoListPanel, DetailPanel
 |- audio: mirrors app.audio, like MainScreen
QueueScreen (ListNav, DetailFocus, ItemActions, AudioBar, AppPages)

FeedLoaderMixin = ListSources + FeedPaging; ItemActionsMixin includes PlaylistRows; AudioController includes AudioQueue and AudioLaunch
```

`ListToolsMixin` runs `f`, `m`/`M`, `D` and `u` over a `Removal` (what a tab's `D` deletes and how it reloads; `MainScreen._removals()` maps tab to `Removal`: History, Library in `src/tui/library_delete.py`, playlists via `PlaylistToolsMixin`). `LibraryRailMixin` drives the rail (All downloads, Videos, Audio, playlists). `QueueScreen` (ListNav, DetailFocus, ItemActions, AudioBar) is the audio queue as a page, pushed over any screen by `q`; `Ctrl+Q` is an app binding that quits through `MainScreen.action_quit_app`.

A mixin declares what it needs from the host (`_LIST_ID`, `_DETAIL_ID`, hooks such as `_worker_start`, `_on_page_shown`, `_on_past_last_page`) in its docstring. Interfaces are listed in each mixin's mirror. A mixin never ships a no-op default for a hook another class provides: an earlier class in the MRO would shadow the real one (this broke Home paging once). `test_mixin_wiring.py` walks the three screens' MRO and fails on an unlisted override, a silent stub, a `self.x` no class provides, a bound key without an action and a message nobody handles; `test_hook_wiring.py` spies on the real hooks through the running screens.

## Worker groups

All are `@work(thread=True, exclusive=True)` unless noted. `exclusive` cancels the earlier worker of the same group on the same node (screen); the thread itself cannot be interrupted, so results are guarded by session counters (below). Network work reaches the UI only through `app.call_from_thread`.

| Group | Screen | Worker | Purpose |
|---|---|---|---|
| `feed_loader` | Main | `_stream_view` | tab load |
| `feed_extend` | Main | `_extend_feed` | next-batch fetch; dropped when `_feed_session` moved on |
| `focus` | Main, Channel | `_detail_worker` | InnerTube metadata for the highlighted row |
| `stream_prefetch` | Main, Channel | `_prefetch_stream_worker` | resolve stream URL ahead of play |
| `thumb` | Main, Channel | `_thumb_worker` | video thumbnail |
| `ch_thumb` | Main | `_avatar_worker` | subscription avatar into the detail panel |
| `ch_focus` | Main | `_channel_info_worker` | channel info for a subscription row |
| `ch_thumb` | Channel | `_avatar_worker` | avatar in the info column |
| `ch_info` | Channel | `_load_channel_info` | channel metadata |
| `ch_content` | Channel | `_load_content` | first page of a tab |
| `ch_extend` | Channel | `_extend_content` | continuation pages |
| `ch_gather` | Channel | `docs/code/src/tui/screens/mixins/channel_playlist.py.md` | playlist play all, queue, save |
| thread `audio-launch` | AudioController | `_launch_worker` | resolve URL, run mpv, retry (plain thread, one per start) |
| thread `audio-poll` | AudioController | `_poll_worker` | read position/duration/pause over IPC every 0.5 s; skipped while the previous poll runs |
| default (not exclusive) | Main | `_run_ytdlp_update` | yt-dlp self-update |
| `video_player`, `mpv_poll` | WatchModal | | foreground mpv (`docs/code/src/tui/screens/watch_modal.py.md`) |
| `download` | DownloadModal | | one download |
| `playlist_row` | Main, Channel | `_load_playlist_worker` | read a playlist row, then play, queue or start a video run |
| `suggest` | SearchModal | | search suggestions as you type |
| `settings_clear` | SettingsModal | | clear-data actions |

## Session counters

A worker is handed a number when it starts and drops its result if the counter has moved on.

| Counter | Owner | Guards | Bumped by |
|---|---|---|---|
| `_focus_session` | `DetailFocusMixin` | `focus` | cursor move, `_kick_focus` |
| `_thumb_session` | `DetailFocusMixin` | `thumb` | cursor move, `_kick_thumb` |
| `_avatar_session` | `MainScreen` | subscription avatar | cursor move, each avatar launch |
| `_info_avatar_session` | `ChannelScreen` | info-column avatar | each `_apply_info` only |
| `_content_session` | `ChannelScreen` | `ch_content` | tab, sort, reload |
| `_feed_session` | `MainScreen` | result of `_extend_feed` | every tab load (`_start_view`) |
| `_session` | `AudioController` | launch, poll, completion, socket path | every audio start |

The channel info avatar must not share a counter the cursor bumps: it does not change with the cursor, and sharing one cancels it mid-load.

## Message flow

| Message | Posted by | Posted on | Handled by |
|---|---|---|---|
| `PlayerStateUpdated`, `AudioTrackChanged`, `AudioQueueChanged`, `AudioSegmentsLoaded` | `AudioController` | every screen on `app.screen_stack` | `AudioBarMixin` handlers |
| `VideoListPanel.Selected` | list highlight | bubbles | `on_video_list_panel_selected` (screen) |
| `VideoListPanel.Activated` | Enter, click on highlighted row, double click | bubbles | `on_video_list_panel_activated` (screen) |
| `VideoListPanel.PageChangeRequested` | page indicator click | bubbles | `ListNavMixin` |
| `DetailPanel.RerenderRequested` | resize (debounced), screen resume | bubbles | `DetailFocusMixin` |

`self.app.post_message(msg)` never reaches a screen. Use `self.app.screen.post_message(msg)`. When `ChannelScreen` is on top, that is the channel screen; the `MainScreen` below gets nothing and updates its own bar directly.

## Data flow per tab

| Tab | Source | Notes |
|---|---|---|
| Home | stash, then disk cache or `ytdlp.fetch_page_batch` (`auth=True`, cookies) | paged, extendable; played videos suppressed (`docs/code/src/tui/screens/mixins/feed_loader.py.md`) |
| Subscriptions | `ytdlp.fetch_subscribed_channels` | rows are channels; avatar and channel info workers per row; detail panel in channel mode |
| Search | `ytdlp.fetch_search_batch` | 50 results at a time up to 200 (continuations as you page), `s` sort and `t` type per search; `SearchStack` (`src/search_stack.py`) holds up to 20 searches for Backspace |
| History | `history.iter_entries` (local), `playlist?list=WL` (Watch Later), YouTube history (`/feed/history`) through the Home loader; the side list picks | local is read off disk; the other two are read-only and need cookies |
| Library (rail: All downloads, Videos, Audio) | `library.all_entries` | local files and `.info.json` sidecars; playback uses `_local_path`, no URL resolution |
| Library rail: playlists (`playlists.json`) | `playlist.py` snapshots + `library.attach_local` | one playlist per rail entry; rows carry their download state |
| Channel and playlist pages | `fetch_channel_info`, `innertube.fetch_channel_page` / `fetch_playlist_page` (token kept in `ChannelPager`) or yt-dlp | pushed `ChannelScreen` |

Cursor move on a video row: `update_basic` immediately; 100 ms later the metadata worker (skipped if the entry has a description); 150 ms later the thumbnail worker.

## Thumbnail pipeline

`thumb_loader.load_thumbnail` runs in a worker and checks `is_current` after each slow step.

- With pixel support (`_HAS_TEXTUAL_IMAGE`): `ensure_thumb_jpeg` (disk cache `~/.cache/termtube/thumbs/<id>.jpg`, then the library sidecar next to `_local_path`, then the CDN), `validate_thumb`, then `set_thumbnail_image` with the path.
- Without: `render_pil_halfblock` at the panel's cell size, with a 64-entry in-memory ANSI cache plus a disk cache; then `set_thumbnail_ansi`.
- Failure: `set_thumbnail_placeholder`.

Channel avatars pass `url=` directly (no entry lookup). `ThumbnailWidget` discards results for an id other than the one set with `set_video_id`.

## Audio pipeline

`a` -> `ItemActionsMixin._play_audio` -> `app.audio.play_audio` -> `_start` (sets `_play_pending`, broadcasts `AudioTrackChanged` so every bar shows "Buffering", starts the 0.5 s poll timer) -> `_launch_worker` (resolve URL without cookies or play `_local_path`; SponsorBlock fetch; headless mpv with a per-session IPC socket; up to 3 attempts with URL re-resolve) -> on exit 0/4 `_on_finished` advances the queue, otherwise `_on_failed`. Every 0.5 s `_poll_worker` reads properties; on the first success the track enters history; each success is broadcast as `PlayerStateUpdated`. Details and stale rules: `docs/code/src/tui/audio_controller.py.md`.

## Common bug locations

- **Thumbnail missing or stuck on "Loading"**: URL empty; session counter shared between workers that should not share one; `ensure_thumb_jpeg` returning None; for library rows, the sidecar missing. Check `is_current` closures first.
- **"Buffering…" never ends**: no successful poll (`poll_audio_properties` returns None: wrong or stale socket path, mpv not up); or a screen missing `AudioBarMixin` (the handlers are `on_player_state_updated` and the `on_audio_*` ones); messages must be posted with `screen.post_message`, never `app.post_message`.
- **Feed empty or not loading**: cookies (`browser` setting, `src/cookies.py`), `ytdlp` options, cache freshness (`cache.is_feed_fresh`), an `ExtractionFailed` on Home opening the update prompt.
- **Play fails or silent**: stale cached stream URL (`streams.re_resolve`), IPC socket path, mpv stderr in the debug log (Ctrl+D, `termtube --debug`).
- **Keys stop working in the list**: focus left the list (`ListNavMixin.on_key` reclaims it for navigation keys only); a modal not dismissed.
- **List reloads when switching tabs**: `tabs.active` assigned to the current tab (see `MainScreen` mirror).
- **UI freezes**: network or file work on the UI thread; `call_from_thread` called from the UI thread.
- **Wrong screen gets a message**: `app.post_message` vs `app.screen.post_message`; `self.app.screen` is the active screen, not necessarily `MainScreen`; `MainScreen` workers and timers keep running while `ChannelScreen` is on top.
