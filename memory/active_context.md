# Active Context

## Current Task: TermTube v2 Clean-Room Rewrite

**Branch:** `v2` (from `main` at commit before rewrite)
**Plan file:** `.cursor/plans/termtube_v2_rewrite_b8d8f6f9.plan.md`

### Phase Status
- [x] Phase 0 — Branch created, directory scaffold complete, requirements.txt updated
- [ ] Phase 1 — Data layer (config, ytdlp, cache, player, cookies, sponsorblock, history)
- [ ] Phase 2 — Textual component library
- [ ] Phase 3 — Main screen + all 5 feed tabs
- [ ] Phase 4 — Playback, modals, settings
- [ ] Phase 5 — Channel drilldown, SponsorBlock UI, bookmarks, notifications
- [ ] Phase 6 — Cross-platform install/uninstall scripts
- [ ] Phase 7 — Docs, tests, CLAUDE.md

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
