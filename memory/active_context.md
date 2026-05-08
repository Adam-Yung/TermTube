# Active Context

## Current Task: TermTube v2 Clean-Room Rewrite

**Branch:** `v2` (from `main` at commit before rewrite)
**Plan file:** `.cursor/plans/termtube_v2_rewrite_b8d8f6f9.plan.md`

### Phase Status
- [x] Phase 0 — Branch created, directory scaffold complete, requirements.txt updated
- [x] Phase 1 — Data layer (config, ytdlp, cache, player, cookies, sponsorblock, history, library, playlist, search_history, hidden, deps, logger, main)
- [x] Phase 2 — TUI component library (app_header, mini_player, page_indicator, progress_bar, thumbnail, video_card, video_list_panel, detail_panel, theme.tcss)
- [x] Phase 3 — MainScreen (5 feed tabs, workers, playback), ChannelScreen, all 9 modals (search, action, error, help, quality, download, playlist, cookies, settings)
- [ ] Phase 4 — SponsorBlock auto-skip at player level, bookmark jump UI, notification bar
- [ ] Phase 5 — Tests (test_cache, test_player, test_ytdlp), CLAUDE.md update, README
- [ ] Phase 6 — setup.sh / uninstall.sh cross-platform install scripts

### Key v2 Architectural Invariants
- ALL yt-dlp Python API calls run inside `@work(thread=True)` — never on the main Textual thread
- yt-dlp Python API used for metadata; subprocess only for downloads
- Cancellation via `threading.Event` + `progress_hook` raising `DownloadCancelled`
- mpv always a separate OS process; TUI controls it via IPC socket only
- `PlayerSession` is the single source of truth for playback state; all UI subscribes
- No chafa dependency — thumbnails are textual-image OR Python color-mosaic
- No suppression system — dedup by video ID within feed pages only
- Default quality: `bestvideo+bestaudio/best` always
- Paged cache keys: `feed_{key}_p{n}`; backward navigation never re-fetches
- Textual `reactive` attributes for widget data binding — no imperative `update_*()` calls
