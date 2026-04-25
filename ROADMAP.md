# TermTube — Roadmap

## Legend
- ✅ Done  · 🔄 In progress  · 📋 Planned  · 💡 Ideas

---

## Phase 1 — Core TUI (✅ Complete)

- ✅ Textual TUI replacing fzf/gum frontend
- ✅ Progressive streaming (yt-dlp → VideoListPanel)
- ✅ Stale-while-revalidate feed cache (instant on repeat visits)
- ✅ Detail panel with thumbnail + metadata + description
- ✅ Video watch (mpv, quality picker)
- ✅ Audio listen (in-TUI NowPlayingModal with IPC seek)
- ✅ Download video/audio with progress bar
- ✅ Search (modal, cached by query hash)
- ✅ History (local watch log)
- ✅ Library (local downloaded files)
- ✅ Playlists (local JSON playlists, drill-down nav)
- ✅ Subscribe (open channel in browser)
- ✅ Cookie auth (cookies.txt priority over browser)

---

## Phase 2 — Quality & Stability (✅ Complete)

- ✅ Lazy loading — VideoListPanel shows 20 at a time, loads more on scroll
- ✅ F1-F7 page navigation (ctrl+digit unreliable in most terminals)
- ✅ Backtick nav picker popup
- ✅ Help tab + HelpScreen modal (full keyboard reference)
- ✅ Seek 0-9 in NowPlayingModal (IPC absolute-percent)
- ✅ textual-image integration — TGP (Kitty) / Sixel (tmux/iTerm2/WezTerm)
- ✅ mpv flicker fix — app.suspend() for video, --really-quiet for audio
- ✅ Quit hang fix — kill_all_active() + os._exit timer
- ✅ Duplicate feed entries fix (removed double on_mount load)
- ✅ Action bar redesigned as bordered panel

---

## Phase 3 — UX Polish (📋 Planned)

### High priority
- 📋 **Thumbnail caching policy** — delete old thumbnails (LRU, configurable max size)
- 📋 **Search history** — remember recent queries, suggest them in the search dialog
- 📋 **Resume position** — store + restore playback position for partially-watched videos
- 📋 **Keyboard shortcut to copy video URL** to clipboard (`y`)
- 📋 **Watch progress indicator** in the video list (e.g. dim progress bar under title)
- 📋 **Channel filter** — press `c` on a video to see more from that channel

### Medium priority
- 📋 **Multi-select** — mark multiple videos for batch download/playlist-add
- 📋 **Sort/filter** — sort list by date, views, duration; filter by watched/unwatched
- 📋 **Comments preview** — show top comments in the detail panel
- 📋 **Related videos** — show related videos in detail panel (from yt-dlp)
- 📋 **Chapters** — show chapter list for long videos, jump to chapter via IPC
- 📋 **Subtitle picker** — choose subtitle language before watching

### Lower priority
- 📋 **Config TUI** — in-app config editor (no YAML editing required)
- 📋 **Notifications** — system notifications (macOS) when downloads complete
- 📋 **mpv playlist** — queue multiple videos and play sequentially
- 📋 **Sponsor block** — integrate SponsorBlock API to skip sponsored segments

---

## Phase 4 — Performance (📋 Planned)

- 📋 **Parallel thumbnail download** — download next N thumbnails while user browses
- 📋 **Feed diff** — on stale-while-revalidate, highlight new videos since last visit
- 📋 **Background search pre-warm** — pre-fetch next page of results while user reads current
- 📋 **Startup time** — profile and reduce cold-start latency (target < 1s to first frame)
- 📋 **Memory cap** — limit _buffer size in VideoListPanel to avoid unbounded growth

---

## Phase 5 — Future Ideas (💡)

- 💡 **Sponsorblock** integration
- 💡 **Return YouTube Dislikes** API integration (show dislike count)
- 💡 **yt-dlp plugin support** — forward yt-dlp plugin flags from config
- 💡 **mpv script integration** — load custom mpv Lua scripts
- 💡 **Keyboard macro recording** — record and replay key sequences
- 💡 **Web UI companion** — serve a minimal REST API for controlling playback remotely

---

## Known Limitations

| Area | Limitation | Workaround |
|---|---|---|
| Thumbnails (Kitty+tmux) | TGP blocked by tmux; sixel used instead (may flicker in some configs) | `set -g allow-passthrough on` in tmux.conf |
| Thumbnails (fallback) | If textual-image not installed, chafa symbols mode used | `pip install textual-image[textual] Pillow` |
| Home feed | yt-dlp buffers all home feed output before streaming (~9s first load) | Subsequent visits use stale cache instantly |
| Safari cookies | macOS sandboxes Safari cookies; yt-dlp cannot read them | Use Chrome/Firefox/Brave in config |
| mpv x265 | Broken x265 dylib on some macOS mpv installs | `brew reinstall ffmpeg` |
| Sixel flicker | Some tmux configs cause sixel flickering | Set `thumbnail_format: symbols` in config |
