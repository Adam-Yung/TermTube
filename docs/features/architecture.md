# Architecture: the wiring map

How the pieces connect. For why a file is written the way it is, read its mirror in `docs/code/`. For settled calls, `docs/decisions/`.

## Layers

| Layer | File | Role |
|---|---|---|
| Entry | `src/main.py` | CLI args, logger, imports `textual_image` before Textual, launches the app |
| App | `src/tui/app.py` | `TermTubeApp`: config and cache, screen push, housekeeping, warm-ups |
| Screens | `src/tui/screens/main_screen.py`, `channel_screen.py` | Thin; compose widgets and mixins |
| Mixins | `src/tui/screens/mixins/` | list navigation, detail focus, item actions, feed loading, audio bar, debug log |
| Audio | `src/tui/audio_controller.py` | `app.audio`: mpv process, queue, polling, SponsorBlock skip |
| Widgets | `src/tui/widgets/` | list, detail panel, action bar, thumbnail, page indicator, header, channel info |
| Keys | `src/tui/keymap.py` | The only definition of the keymap in code (`docs/features/keybindings.md`) |
| Messages | `src/tui/messages.py` | `PlayerStateUpdated`, `AudioTrackChanged`, `AudioQueueChanged`, `AudioSegmentsLoaded`: the audio controller broadcasts them to every screen on the stack |
| Thumbnails | `src/tui/thumb_loader.py`, `src/ui/thumbnail.py` | worker-side thumbnail loading; fetch, validate, half-block render |
| yt-dlp | `src/ytdlp.py` (opts, feeds, search, channels), `src/cookies.py`, `src/downloads.py`, `src/streams.py` | all extraction; `streams.py` resolves and caches playback URLs |
| InnerTube | `src/innertube.py` | fast video details and channel browse without yt-dlp |
| Player | `src/player.py` | mpv command lines, IPC, polling |
| Row types | `src/entries.py` | `TypedDict`s for video, channel, playlist and library rows (annotations only) |
| Data | `src/cache.py`, `src/history.py`, `src/library.py`, `src/playlist.py`, `src/config.py` | disk and RAM state |
| Platform | `src/plat.py` | paths, clipboard, process registry, IPC paths |

## Screens and mixins

```
MainScreen (ListTools, ListNav, DetailFocus, ItemActions, AudioBar, FeedLoader, DebugLog)
 |- AppHeader, Tabs, VideoListPanel, DetailPanel (ThumbnailWidget + ActionBar), RichLog
 |- pushes: ChannelScreen, WatchModal, DownloadModal, SearchModal, SettingsModal, HelpScreen, ...
ChannelScreen (ListNav, DetailFocus, ItemActions, AudioBar)
 |- ChannelInfoPanel, Tabs, VideoListPanel, DetailPanel
 |- audio: mirrors app.audio, like MainScreen
```

A mixin declares what it needs from the host (`_LIST_ID`, `_DETAIL_ID`, hooks such as `_worker_start`, `_on_last_page_reached`) in its docstring. Interfaces are listed in each mixin's mirror.

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
| `ch_content` | Channel | `_load_content` | videos or playlists |
| thread `audio-launch` | AudioController | `_launch_worker` | resolve URL, run mpv, retry (plain thread, one per start) |
| thread `audio-poll` | AudioController | `_poll_worker` | read position/duration/pause over IPC every 0.5 s; skipped while the previous poll runs |
| default (not exclusive) | Main | `_run_ytdlp_update` | yt-dlp self-update |
| `video_player`, `mpv_poll` | WatchModal | | foreground mpv (`docs/code/src/tui/screens/watch_modal.py.md`) |
| `download` | DownloadModal | | one download |

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

The channel info avatar must not share a counter the cursor bumps: it does not change with the cursor, and sharing one cancels it mid-load (fixed in ccebfaa).

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
| Search | `ytdlp.fetch_search_batch` | 50 results, extendable; `SearchStack` (`src/search_stack.py`) holds up to 20 searches for Backspace |
| History | `history.iter_entries` | local |
| Library | `library.all_entries` | local files and `.info.json` sidecars; playback uses `_local_path`, no URL resolution |
| Playlists | `playlist.py` + cached entries | index list, then one playlist (Backspace returns) |
| Channel page | `fetch_channel_info`, InnerTube browse or `fetch_channel_videos` | pushed `ChannelScreen` |

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
- **Feed empty or not loading**: cookies (`browser` setting, `src/cookies.py`), `ytdlp` options, cache freshness (`cache.is_feed_fresh`), the `_EXTRACTION_ERRORS` match opening the update prompt.
- **Play fails or silent**: stale cached stream URL (`streams.re_resolve`), IPC socket path, mpv stderr in the debug log (Ctrl+D, `termtube --debug`).
- **Keys stop working in the list**: focus left the list (`ListNavMixin.on_key` reclaims it for navigation keys only); a modal not dismissed.
- **List reloads when switching tabs**: `tabs.active` assigned to the current tab (see `MainScreen` mirror).
- **UI freezes**: network or file work on the UI thread; `call_from_thread` called from the UI thread.
- **Wrong screen gets a message**: `app.post_message` vs `app.screen.post_message`; `self.app.screen` is the active screen, not necessarily `MainScreen`; `MainScreen` workers and timers keep running while `ChannelScreen` is on top.
