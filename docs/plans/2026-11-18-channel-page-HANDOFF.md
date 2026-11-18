# Handoff: channel page (todo items P7.1 and P7.2)

Self-contained work for a separate agent. Source of intent: `docs/plans/2026-11-17-ux-and-performance-audit-PLAN.md`, section B2.
Master record: `docs/todo.md` (tick items there). Work on a branch cut from `audit-impl` (for example `audit-channel`); merge back is the owner's call.

## Rules that bind this work

- `AGENTS.md` is the source of truth for code, docs, comments and tests. Read it first. Every commit passes `scripts/verify.sh` (prints `GATE-OK`).
- **Hard rule:** no downloads of any kind (no pip, no git clone, no data or model fetches), no network in tests, no real browser profile, no real `~/.config` or `~/.cache`. InnerTube parsers are written against fixture JSON files trimmed from responses the owner records; the agent never calls YouTube. If a fixture is missing, write the parser from the documented shape, mark it `[verify live]` in `docs/decisions/feeds-and-paging.md`, and say so in the report.
- Sonnet or smaller only. No subagents. Keep tool output small.
- Tests must not rely on wall-clock timing (Windows CI is slow): drive timers explicitly, patch `DetailFocusMixin._kick_focus` and `_kick_thumb` in TUI tests as `src/tests/tui/test_list_tools.py` does.
- Reuse what exists; do not copy: `JsonStore` (`src/store.py`), `fuzzy` (`src/fuzzy.py`), `SortModal(options, title)`, `ListToolsMixin` (filter `f`, marks, `D`, `u`), `FeedLoaderMixin._ui` (view-session guard), `panel.next_page_number`.
- A new key goes in `src/tui/keymap.py`, `help_screen.py`, the action bar and `docs/features/keybindings.md` together; the key-consistency test enforces it. Free keys: `Q` is reserved for the queue view, `J`/`K` for reordering; check `keymap.py` before binding anything.

## Current state (read the mirrors before editing)

Files: `src/tui/screens/channel_screen.py`, `src/innertube.py`, `src/ytdlp.py` (`fetch_channel_*`), `src/entries.py`, mirrors under `docs/code/`.

- Channel page: tabs Videos and Playlists, sort `s` (date via InnerTube, other sorts via yt-dlp), reload `r`, back `Esc`.
- `innertube.fetch_channel_videos(channel_id)` returns about 30 videos and follows no continuation. `fetch_channel_playlists` follows continuations up to 80.
- `ChannelScreen._channel_id` parses the URL by string splitting.
- Enter on a channel playlist row has no destination.

## Tasks

### P7.1 Channel content
1. Follow InnerTube continuations for channel videos with the same prefetch-ahead model as the Home list (fetch when the user reaches the second-to-last page; cap 200; no re-reading of earlier pages: keep the continuation token). Show `Page 3 / 4 · loading 40 more…` style progress in the footer.
2. Shorts and Live/Streams tabs through the browse tab params; hide a tab the channel does not have. Parsers reuse the video parser where the shape matches.
3. Sort: implement the InnerTube popular/oldest filter chips, or remove the unused `sort` argument and route non-date sorts to yt-dlp explicitly. State which in the decision log.
4. Channel info column: description (first 3 lines, `a` or Enter expands), join date, video count, from the same `/browse` response (no new request).
5. Back stack with breadcrumb (`Home › Name › Playlists`) so a channel opened from a channel's video can return to its origin.
6. Replace `_channel_id` string splitting with one tested helper (`/channel/UC…`, `/@handle`, `/c/…`, `/user/…`).

### P7.2 Channel navigation and queueing
1. Enter on a channel playlist row opens it as a playable list (InnerTube browse of the playlist, yt-dlp fallback), with play all, enqueue all (`E`; reuse the audio controller queue API and check what bulk call exists) and "save to local playlist" (reuse `src/playlist.py`).
2. Local channel bookmarks: `channels.json` via `JsonStore` (id, name, avatar url, added). A key to bookmark or unbookmark on the channel page and a "Following (local)" view reachable from the Subscriptions tab, so it works with `browser: none`. Do not change the existing Subscriptions behaviour (the owner decided it stays: list the channels, Enter opens the channel).

## Done when

- Every item has tests (parsers on fixtures, continuation stop conditions, tab hiding, breadcrumb, bookmarks round trip, key consistency) and regression tests for existing channel behaviour.
- Mirrors, `docs/features/*`, `docs/status.md` (present reality only) and the decision log are updated in the same commits.
- `scripts/verify.sh` is green before every commit; nothing is pushed unless the owner says so.
- Report under 200 words: items done with commit hashes, anything marked `[verify live]`, anything blocked.
