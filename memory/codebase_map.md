# TermTube Codebase Map

> **MANDATORY READ** — Every AI agent MUST read this file before making any changes.
> After confirming a fix or implementing a feature, update this file if any section is
> inaccurate or incomplete. This is the single source of truth for codebase understanding.

---

## Quick Reference

| Layer | Key File(s) | Responsibility |
|-------|-------------|----------------|
| Entry point | `src/main.py` | CLI args, logger setup, launches `TermTubeApp` |
| App shell | `src/tui/app.py` | `TermTubeApp(App)` — config/cache on app, screen push, housekeeping |
| Main screen | `src/tui/screens/main_screen.py` | Tabs, feed loading, detail panel, audio playback, all worker orchestration |
| Channel screen | `src/tui/screens/channel_screen.py` | Pushed screen for browsing a single channel (info + videos + playlists) |
| yt-dlp wrapper | `src/ytdlp.py` | All YouTube data extraction — feeds, search, channels, stream URLs, downloads |
| InnerTube | `src/innertube.py` | Direct YouTube InnerTube API (fast metadata, no yt-dlp overhead) |
| Player | `src/player.py` | mpv IPC — launch, send commands, poll state (position/duration/paused) |
| Thumbnails | `src/ui/thumbnail.py` | Download + PIL half-block render + local sidecar resolution |
| Cache | `src/cache.py` | Disk + RAM cache for feeds, video metadata, thumbnails |
| Library | `src/library.py` | Scans ~/Documents/TermTube/ for downloaded media + .info.json sidecars |
| Config | `src/config.py` | YAML config at ~/.config/TermTube/config.yaml |
| Platform | `src/plat.py` | OS abstraction — paths, clipboard, process registry, thumbnail download |

---

## Architecture Wiring

```
User Input → MainScreen (keybindings/messages)
                ├── VideoListPanel (cursor navigation, page loading)
                ├── DetailPanel (metadata display, thumbnail widget, action bar)
                ├── Workers:
                │   ├── feed_loader (group="load") — yt-dlp feed/search/subs fetch
                │   ├── focus (group="focus") — InnerTube metadata + stream prefetch
                │   ├── thumb (group="thumb") — video thumbnail download + render
                │   ├── ch_thumb (group="ch_thumb") — channel avatar download + render
                │   ├── ch_focus (group="ch_focus") — channel info fetch
                │   ├── audio_poll (group="audio_poll") — 0.5s mpv IPC polling
                │   └── audio_launch (group="audio") — start mpv + wait for EOF
                └── Screens pushed:
                    ├── ChannelScreen — full channel browser
                    ├── WatchModal — video playback (app.suspend → mpv)
                    ├── DownloadModal — download progress
                    ├── SearchModal — search input
                    └── SettingsModal, HelpScreen, etc.
```

### Worker Groups (exclusive=True means latest-wins)

| Group | File | Purpose | Notes |
|-------|------|---------|-------|
| `load` | main_screen | Feed/search/subs loading | One feed at a time |
| `focus` | main_screen | InnerTube metadata fetch | Fires after 100ms dwell |
| `thumb` | main_screen | Video thumbnail render | Fires after 150ms dwell; uses `_thumb_session` counter |
| `ch_thumb` | main_screen | Channel avatar render | Dedicated group + dedicated `_ch_thumb_session` counter — never cross-cancels with video thumbs |
| `ch_focus` | main_screen | Channel info fetch | For subscriptions detail panel |
| `audio_poll` | main_screen | mpv IPC status poll | 0.5s interval timer drives it |
| `audio` | main_screen | mpv audio launch + EOF wait | |
| `stream_prefetch` | main_screen | Pre-resolve stream URLs | Background, doesn't block UI |
| `ch_info` | channel_screen | Channel metadata fetch | |
| `ch_content` | channel_screen | Channel videos/playlists | |
| `ch_thumb` | channel_screen | Channel avatar (on channel page) | |
| `ch_detail_focus` | channel_screen | Video metadata in channel view | |
| `ch_detail_thumb` | channel_screen | Video thumbs in channel view | |

### Message Flow

| Message | Posted from | Posted on | Received by |
|---------|------------|-----------|-------------|
| `PlayerStateUpdated` | `_poll_audio_ipc_threaded` | `self.app.screen` (active screen) | `ChannelScreen.on_term_tube_app_player_state_updated` |
| `VideoListPanel.Selected` | VideoListPanel | bubbles up | `MainScreen.on_video_list_panel_selected` |
| `DetailPanel.RerenderRequested` | DetailPanel (on resize) | bubbles up | `MainScreen.on_detail_panel_rerender_requested` |
| `DetailPanel.ChannelClicked` | DetailPanel | bubbles up | `MainScreen.on_detail_panel_channel_clicked` |

**Critical Textual routing rule:** `self.app.post_message(msg)` does NOT propagate to screens. Use `self.app.screen.post_message(msg)` to reach the currently active screen.

---

## Data Flow Per Tab

### Home / Search / History / Playlists (video feeds)
```
Tab selected → _stream_view() → @work(group="load") fetches entries
  → panel.add_page(entries) → panel.load_page(1)
  → User focuses entry → 100ms dwell → _kick_focus → InnerTube fetch
  → 150ms dwell → _kick_thumb → _thumb_worker downloads + renders thumbnail
```

### Subscriptions (channel list)
```
Tab selected → _load_subscriptions_channels() → ytdlp.fetch_subscribed_channels()
  → panel.add_page(entries with _is_channel=True)
  → User focuses channel → on_video_list_panel_selected detects _is_channel
  → detail.update_channel_entry() + detail.set_thumbnail_loading()
  → _kick_channel_info():
      - If entry has thumbnail URL → _channel_thumb_worker (group="ch_thumb") downloads avatar
      - If entry lacks description → _channel_info_worker (group="ch_focus") fetches full info
        → _apply_ch_info_to_detail merges + kicks _channel_thumb_worker with avatar URL
```

### Library (offline downloads)
```
Tab selected → library.all_entries() scans .info.json sidecars (pure filesystem, no network)
  → Entries have _local_path, _local_type, _sidecar_path
  → User focuses entry → 150ms dwell → _thumb_worker:
      1. Check cache: ~/.cache/termtube/thumbs/{vid}.jpg
      2. Check local sidecar: _resolve_local_thumb() finds thumbnail next to media file
      3. Fallback: download from URL in entry (only if offline sources exhausted)
  → Playback uses _local_path directly (--no-ytdl), never resolves stream URLs
```

### Channel Page (pushed screen)
```
MainScreen._open_channel() → app.push_screen(ChannelScreen)
  → _load_channel_info() fetches avatar + metadata (no cookies needed)
  → _apply_info() displays info + kicks _fetch_channel_thumb (group="ch_thumb")
  → _load_content() fetches channel videos/playlists
  → Audio state synced via _sync_audio_state() on mount
  → Progress updates via PlayerStateUpdated message from MainScreen
```

---

## Thumbnail Pipeline

Two rendering backends (auto-detected at import time):

1. **textual-image** (`_HAS_TEXTUAL_IMAGE = True`): Pixel-perfect via Kitty/Sixel protocol.
   Widget receives a file path → renders natively.
2. **PIL half-block** (fallback): 24-bit ANSI `▀` characters. Works everywhere.
   Rendered ANSI cached at `~/.cache/termtube/rendered/{vid}_{cols}x{rows}_pil.ansi`.

Canonical resolution logic lives in `thumbnail.py`:
- **`ensure_thumb_jpeg(vid, entry, url)`** — single resolution chain used by all 4 workers:
  1. `_thumb_path(vid)` → `~/.cache/termtube/thumbs/{vid}.jpg` (disk cache)
  2. `_resolve_local_thumb(vid, entry)` → sidecar adjacent to `_local_path` (library only)
  3. `download(vid, url)` → network download from YouTube CDN
- **`validate_thumb(path)`** — PIL decode check (catches corrupt downloads)
- **`_best_thumb_url(entry)`** — canonical URL extractor (single copy; ytdlp.py imports from here)

Session counter isolation (MainScreen):
- `_thumb_session` — guards `_thumb_worker` (group="thumb", video thumbnails)
- `_ch_thumb_session` — guards `_channel_thumb_worker` (group="ch_thumb", channel avatars)
- `_cancel_pending_focus_and_thumb()` bumps BOTH on cursor move

Channel avatars use a **dedicated** `_channel_thumb_worker` (group="ch_thumb") that takes the URL directly — never goes through `_best_thumb_url`.

---

## Audio Playback Pipeline

```
User presses 'l' (listen) → _start_audio(entry)
  → _audio_playing = True, _play_pending = True
  → ActionBar switches to player mode (shows "Buffering...")
  → _audio_poll_timer = set_interval(0.5s, _poll_audio_ipc)
  → _launch_audio_worker:
      1. Resolve stream URL (check cache → yt-dlp resolve, NO cookies)
      2. CDN warmup probe
      3. Spawn mpv with --input-ipc-server
      4. _play_pending = False
      5. Wait for mpv EOF
      6. On finish → advance queue or _stop_audio()
  → Every 0.5s: _poll_audio_ipc → poll_audio_properties (IPC socket)
      → update ActionBar (pos/dur/paused)
      → post PlayerStateUpdated to active screen
```

**Key facts:**
- Stream URL resolution does NOT use cookies (public CDN URLs)
- `_local_path` entries skip URL resolution entirely (play local file)
- ActionBar shows "Buffering..." when `_dur == 0` (mpv hasn't reported duration yet)
- Poll only posts updates when BOTH pos and dur are not None

---

## Common Bug Locations

### "No thumbnail" / stuck "Loading"
- Check `_thumb_worker` or `_channel_thumb_worker` — is the URL empty? Is the worker group conflicting?
- Check `ensure_thumb_jpeg(vid, entry)` — does it return a valid path?
- Verify session counters are independent: `_thumb_session` for video thumbs, `_ch_thumb_session` for channel avatars (MainScreen). Shared counter was a past regression (fixed in ccebfaa).
- For channels: must use `_channel_thumb_worker` (group="ch_thumb"), NOT `_thumb_worker` (group="thumb")
- For library: check `_resolve_local_thumb` — is the sidecar thumbnail file present?

### "Buffering..." stuck in Now Playing
- Check if `_poll_audio_ipc_threaded` is actually running (timer on MainScreen)
- Check if `poll_audio_properties` returns `(None, None, False)` — socket issue
- Check if `PlayerStateUpdated` is posted on `self.app.screen` (NOT `self.app`)
- On ChannelScreen: message must reach `on_term_tube_app_player_state_updated`

### Feed not loading / empty
- Check `_make_ydl()` — cookies needed for authenticated feeds (home, subscriptions)
- Check `_base_opts()` for extractor_args
- Check cache staleness in `cache.py`

### Playback fails / no audio
- Check stream URL cache: `get_cached_stream_url()` might return stale URL
- Check `_audio_socket()` path — is mpv actually listening?
- Check `player.py` — `_get_persistent_socket` timeout/connection
- For local files: verify `_local_path` exists and mpv supports the format

### UI frozen / unresponsive
- A `@work(thread=True)` call is blocking the main thread via `call_from_thread`
- A synchronous network call leaked into the main thread
- Check for uncaught exceptions in worker `finally` blocks

### Screen navigation bugs
- Workers on MainScreen continue when ChannelScreen is pushed (timers still fire)
- `self.app.screen` returns the ACTIVE screen, not necessarily MainScreen
- Widget queries (`self.query_one(...)`) can fail if screen is not mounted

---

## Configuration

Config at `~/.config/TermTube/config.yaml`. Key fields:

| Key | Default | Purpose |
|-----|---------|---------|
| `browser` | `"auto"` | Browser for cookie extraction. `"none"` = no auth |
| `theme` | `"crimson"` | UI theme (crimson/amber/ocean/midnight) |
| `video_dir` | `~/Documents/TermTube/Video` | Download location for video |
| `audio_dir` | `~/Documents/TermTube/Audio` | Download location for audio |
| `sponsorblock_auto_skip` | `true` | Auto-skip sponsor segments |
| `prefetch_video` | `false` | Pre-resolve video format URLs (slower, uses more bandwidth) |

---

## yt-dlp Usage Patterns

| Function | Cookies? | Purpose |
|----------|----------|---------|
| `fetch_home_feed()` | YES (via `_make_ydl`) | Personalized home feed |
| `fetch_subscribed_channels()` | YES | User's subscriptions |
| `fetch_channel_info()` | NO (plain `YoutubeDL`) | Public channel metadata |
| `fetch_channel_videos()` | YES | Channel's video listing |
| `resolve_stream_url()` | NO | CDN URL resolution (public) |
| `search_videos()` | YES | Search results |
| `download_video()` | NO | Download media |

---

## Self-Update Protocol

When you (the AI agent) make changes:

1. **If you add/remove a worker group** → update the Worker Groups table above
2. **If you change message routing** → update the Message Flow table
3. **If you fix a bug related to a "Common Bug Location"** → update/add the resolution
4. **If you add a new file** → update the Quick Reference table
5. **If you change how thumbnails, audio, or feeds work** → update the relevant pipeline section
6. **If you discover this document is wrong** → fix it immediately after confirming the fix works

Never let this document drift from reality.
