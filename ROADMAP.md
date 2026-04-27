# TermTube — Roadmap

## Legend
- ✅ Done  · 🔄 In progress  · 📋 Planned  · 💡 Ideas

---

## v0.1 — Foundation (✅ Complete)

### Core TUI
- ✅ Textual TUI replacing fzf/gum frontend
- ✅ Progressive streaming (yt-dlp → VideoListPanel, batches of 20)
- ✅ Stale-while-revalidate feed cache (instant on repeat visits)
- ✅ Detail panel with thumbnail + metadata + description
- ✅ F1–F7 page navigation + backtick nav picker popup
- ✅ Help screen with full keyboard reference (?)
- ✅ Settings modal — theme, quality, thumbnail format, browser, OAuth2

### Playback
- ✅ Video watch via WatchModal — mpv window + in-TUI IPC progress bar
- ✅ Audio listen — embedded ActionBar player, mpv headless via IPC socket
- ✅ Audio queue — `e` to enqueue, `>` to skip, auto-advance at end of track
- ✅ Seek controls — `h/l` ±5s, `H/L` ±10s, `0–9` absolute-percent
- ✅ Pause/resume — Space
- ✅ Quality picker modal (Watch/Listen)

### Data & Cache
- ✅ Home feed + Subscriptions (yt-dlp flat-playlist, cookie auth)
- ✅ Search (cached by query hash, instant repeat searches)
- ✅ History (local watch log, shown as "watched Xd ago" in list)
- ✅ Library (local downloaded files, video + audio)
- ✅ Playlists (local JSON playlists, drill-down nav with backspace)
- ✅ LRU suppression — home feed hides videos focused 3× or watched
- ✅ Background refresh — home feed silently refetched every 10 min
- ✅ Thumbnail cache with LRU pruning (7-day TTL, 300-item cap)
- ✅ Video metadata cache with TTL pruning (3-day TTL, 400-item cap)
- ✅ Parallel thumbnail pre-download during background enrichment

### Actions
- ✅ Download video / audio with live TUI progress bar (DownloadModal)
- ✅ Copy video URL to clipboard — `y` (pbcopy / xclip / wl-copy fallback)
- ✅ Open channel in browser — `s` (subscribe)
- ✅ Open video in browser — `b`
- ✅ Add video to playlist — `p`
- ✅ Cookie auth (cookies.txt priority over browser session)

### Graphics
- ✅ textual-image integration — TGP (Kitty) / Sixel support
- ✅ chafa ANSI block fallback (universal compatibility)
- ✅ tmux detection — forces chafa symbols to avoid sixel corruption
- ✅ Cached thumbnail swap — no loading flash on re-visit

### Technical
- ✅ mpv IPC controller (non-blocking audio, clean quit/seek)
- ✅ Quit hang fix — kill_all_active() + os._exit timer
- ✅ app.suspend() for video (clean terminal handoff to mpv)
- ✅ Atomic cache writes (tmp + os.replace)
- ✅ enrich_in_background — lazy metadata + thumbnail pre-fetch per scroll batch

---

## v0.2 — Polish Release (📋 In progress)

### Blockers before tagging 0.2.0

**Dead code to remove** (never called from any screen):
- 📋 `src/tui/screens/now_playing.py` — `NowPlayingModal` is orphaned; audio moved to embedded ActionBar
- 📋 `src/ytdlp.py` — `download_video()`, `download_audio()` (bare variants without progress), `get_stream_url()`, `subscribe_channel()`, `open_in_browser()`
- 📋 `src/ui/thumbnail.py` — `download_background()` is never called (enrich_in_background calls `download()` directly)
- 📋 `src/tui/screens/main_screen.py` — `action_subscribe()` (dead wrapper for `action_subscribe_entry()`), empty `if TYPE_CHECKING: pass` block
- 📋 `src/tui/widgets/video_list.py` — empty `if TYPE_CHECKING: pass` block

**Help screen gaps** (shortcuts exist but are undocumented):
- 📋 `y` — Copy URL missing from help screen DOWNLOADS section
- 📋 `e` / `>` — Audio queue / skip missing from help screen PLAYBACK section
- 📋 Mention audio queue in ActionBar actions grid

**Config/README:**
- 📋 README: replace `yourname/termtube` placeholder with real GitHub URL
- 📋 Fix `DEFAULT_CONFIG` vs property fallback mismatch: `browser` defaults to `"firefox"` in the YAML but `"chrome"` in the property fallback — pick one
- 📋 Roadmap already updated (this file)

### High Priority UX

- 📋 **Search history** — remember last N queries in SearchModal; ↑/↓ to cycle through them
- 📋 **Memory cap** — `VideoListPanel._buffer` is unbounded; cap at ~500 entries to avoid slow scrolls on very long feeds
- 📋 **Channel filter** — press `c` on a video to filter the current list to that channel only (in-memory, no network call); `Esc` / `c` again to clear

### Medium Priority

- 📋 **Watch progress indicator** — subtle dim bar or `▶` glyph in VideoListItem for videos in history
- 📋 **Resume position** — store + restore mpv playback position for partially-watched videos
- 📋 **Feed diff** — on stale-while-revalidate, mark new-since-last-visit videos with a subtle badge

---

## v0.3 — Depth (💡 Future)

- 💡 **Multi-select** — mark multiple videos for batch download or playlist-add
- 💡 **Sort / filter** — sort list by date, views, duration; filter by watched/unwatched
- 💡 **Chapters** — show chapter list for long videos, jump to chapter via IPC seek
- 💡 **Subtitle picker** — choose subtitle language before watching
- 💡 **Comments preview** — show top comments in detail panel (yt-dlp can fetch these)
- 💡 **Related videos** — show related/recommended videos in detail panel
- 💡 **SponsorBlock** — integrate SponsorBlock API to auto-skip sponsored segments
- 💡 **System notifications** — macOS/Linux notification when a download completes
- 💡 **Video playlist queue** — queue multiple videos and play sequentially (audio queue already works; video is harder due to app.suspend())
- 💡 **Background search pre-warm** — pre-fetch next page of results while user reads current
