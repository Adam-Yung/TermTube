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

### Recently completed
- ✅ **Paged video list** — replaced infinite scroll with a fixed 20-entry page system. `]`/`[` to navigate pages, `g`/`G` for first/last page. Background pre-fetches next 80 entries. Exit stash ensures instant boot with fresh content.
- ✅ **Leaner cache** — metadata capped at 100 entries (FIFO), stash holds exactly 20 entries for next boot.
- ✅ **Honest loading indicator** — header spinner animates whenever any worker is active (reference counted).
- ✅ **100ms metadata debounce** — snappy detail panel updates with cancel-before-start.
- ✅ **SponsorBlock integration** — sponsor segments highlighted in green on progress bars (audio ActionBar + video WatchModal). Auto-skip enabled by default. Configurable categories (sponsor, selfpromo). Segments cached locally for 24h.

### Blockers before tagging 0.2.0

** Setup Script **:
- Add support for updates
- Help message should be a HereDoc instead of multiple echo commands

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
- 💡 **System notifications** — macOS/Linux notification when a download completes
- 💡 **Video playlist queue** — queue multiple videos and play sequentially (audio queue already works; video is harder due to app.suspend())

---

## v0.4 — Platform & Integrations (📋 Planned)

- 📋 **Search in Library/History** — a pressable/enterable search field at the top of the video list in Library and History tabs. Filters locally through saved/watched videos without network calls.
- 📋 **Channel browsing** — dedicated channel view: channel info + description on the left panel, channel's videos on the right panel with sub-tabs for "Videos" and "Playlists", sortable by latest/most popular.
- 📋 **Remove header gap** — eliminate the horizontal gap between the Tabs header bar and the video list / detail panels; consolidate into a seamless, space-efficient layout.
- 📋 **Robust install/uninstall scripts** — cross-platform dependency installation (brew, apt, pacman, winget), prompt user for sync mode during install, complete and secure uninstallation that removes all traces.
- 📋 **Best quality as default** — ensure `preferred_quality: "best"` is the documented and enforced default for both video and audio playback.
- 📋 **Code audit** — thorough audit of the entire codebase for performance bottlenecks, security issues (cookie handling, subprocess injection), and stability (error recovery, graceful degradation).
- 📋 **Windows support** — full Windows compatibility via winget for dependency installation. Windows Terminal supports Sixel/images natively. Handle path separators, socket paths (`\\.\pipe\` instead of Unix sockets), and process management differences.
