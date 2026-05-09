# Active Context

## Current Task: TermTube v2 Clean-Room Rewrite

**Branch:** `v2` (from `main` at commit before rewrite)
**Plan file:** `.cursor/plans/termtube_v2_rewrite_b8d8f6f9.plan.md`

### Phase Status
- [x] Phase 0 — Branch created, directory scaffold complete, requirements.txt updated
- [x] Phase 1 — Data layer (config, ytdlp, cache, player, cookies, sponsorblock, history, library, playlist, search_history, hidden, deps, logger, main)
- [x] Phase 2 — TUI component library (app_header, mini_player, page_indicator, progress_bar, thumbnail, video_card, video_list_panel, detail_panel, theme.tcss)
- [x] Phase 3 — MainScreen (5 feed tabs, workers, playback), ChannelScreen, all 9 modals (search, action, error, help, quality, download, playlist, cookies, settings)
- [x] Phase 4 — PlayerSession observe_property, MiniPlayer unified audio+video, DownloadModal, SettingsModal (5 sections), CookiesModal wizard, HelpScreen (searchable), ErrorModal
- [x] Phase 5 — Channel subscribe/unsubscribe + avatar, SponsorBlock auto-skip + ticks, bookmarks (m key + DetailPanel + ProgressBar), format memory (auto-select last quality), NotificationBar (persistent errors), queue (e/> keys), seek 0-9, cookie freshness auto-check
- [x] Phase 6 — Cross-platform setup.sh (OS detect, brew/apt/dnf/pacman, Python 3.11+ check, auto-install mpv/ffmpeg, venv, sync prompt, symlink) + uninstall.sh (kill, remove, interactive prompts, summary) + setup.ps1 Windows stub
- [ ] Phase 7 — Tests, CLAUDE.md update, README rewrite

### Key v2 Architectural Invariants
- ALL yt-dlp Python API calls run inside `@work(thread=True)` — never on the main Textual thread
- yt-dlp Python API used for metadata; subprocess only for downloads
- Cancellation via `threading.Event` + `progress_hook` raising `DownloadCancelled`
- mpv always a separate OS process; TUI controls it via IPC socket only
- Video playback opens a separate mpv window — NO app.suspend(), TUI stays fully live
- `PlayerSession` is the single source of truth for playback state; all UI subscribes
- No chafa dependency — thumbnails are textual-image OR Python color-mosaic
- No suppression system — dedup by video ID within feed pages only
- Default quality: `bestvideo+bestaudio/best` always; format memory auto-selects last choice
- Paged cache keys: `feed_{key}_p{n}`; backward navigation never re-fetches
- Textual `reactive` attributes for widget data binding — no imperative `update_*()` calls
- Playback queue: `e` enqueues, `>` skips, auto-advance on track end
- NotificationBar: ephemeral toasts auto-dismiss; errors persist until Esc, E opens detail modal
