# src/tui/screens/mixins/detail_focus.py

Fills the detail panel for the row under the cursor, without a request per row while the user holds `j`. Decisions: `docs/decisions/thumbnails.md`, `docs/decisions/concurrency.md`.

## Flow

`_focus_video(entry)`:
1. `DetailPanel.update_basic` paints title/channel/stats from the cached entry at once.
2. `_cancel_pending_focus_and_thumb` stops both dwell timers and bumps the session counters.
3. The thumbnail timer fires after 150 ms (`THUMB_DWELL_S`), the metadata timer after 100 ms (`FOCUS_DWELL_S`). Each re-checks `detail.current_id == vid` and starts its worker with a fresh session number.

Placeholder ids (`__playlist__...`) get no timers and no workers.

A playlist row (not a Mix, whose row carries its first video's thumbnail) that has no thumbnail takes the `FOCUS_DWELL_S` timer too, but `_kick_playlist` starts `_playlist_header_worker` (group `focus`, one `browse` request) instead of a video-details fetch. yt-dlp's Home rows for playlists carry neither; the worker merges the header's thumbnail, description and video count into the row, caches it, marks it `_header_read` (so it is read once) and re-kicks the thumbnail.

## Session counters

| Counter | Guards | Bumped by |
|---|---|---|
| `_focus_session` | `_detail_worker` (group `focus`) | every cursor move; `_kick_focus` |
| `_thumb_session` | `_thumb_worker` (group `thumb`) | every cursor move; `_kick_thumb` |

A worker captures its number at start and passes `is_current=lambda: session == self._thumb_session` to `load_thumbnail`, which checks it after each slow step (download, render). A cursor move bumps the counter, so a result for a row the user has left is dropped, even though the thread cannot be killed (`exclusive=True` cancels the worker object, not a blocking network call).

The counters are bumped twice per row on purpose: once on cursor move (cancel everything pending), once in `_kick_*` (identify this worker). Do not remove the second bump: a re-render after a resize starts a new worker for the same row and must cancel the old one.

`MainScreen` adds a third counter, `_avatar_session`, for subscription avatars (see `docs/code/src/tui/screens/main_screen.py.md`). `ChannelScreen` keeps its channel-info avatar on `_info_avatar_session`, which a cursor move never touches. The info panel avatar does not change with the cursor; sharing the cursor-bumped counter would cancel it the first time the user moves the cursor while it loads (the cross-worker cancellation race fixed in ccebfaa).

## Worker groups (all `thread=True, exclusive=True`)

| Group | Worker | Notes |
|---|---|---|
| `focus` | `_detail_worker` | InnerTube metadata (`innertube.fetch_video_details`), merged into the entry, written to the cache, pushed to the list row and the panel. Skipped when the entry already has a description. Also starts the stream prefetch. |
| `stream_prefetch` | `_prefetch_stream_worker` | Resolves the stream URL (`streams.prefetch_stream_url`; it called a removed `ytdlp` name and failed silently until 2026-11-18) (and the `bv+ba/b` URL if `prefetch_video`) so the first play is fast. A newer prefetch replaces an older one. |
| `thumb` | `_thumb_worker` | `thumb_loader.load_thumbnail`, entry-based (local sidecar, cache, then network). |

`_worker_start`/`_worker_end` are hooks; `MainScreen` implements them to drive the header spinner. `ChannelScreen` does not show a spinner.

## Messages

`DetailPanel.RerenderRequested` (resize, screen resume) is handled here: the thumbnail restarts after a 300 ms debounce, sharing `_thumb_dwell_timer` with the cursor path so a resize drag and a cursor move cancel each other.
