# Playlist pages

Append-only, dated.

## 2026-11-22 — Playlist pages are a mode of the channel page; Home and Search rows open them

Reverses the 2026-11-17 call in [ui.md](ui.md) that playlist rows from search do not open in the app ("a remote playlist has no loader here"): the
channel page already loads a playlist's videos, so there is a loader. Owner decisions: no new screen class (`ChannelScreen` gets a playlist
mode, tabs, sort and follow hidden); the page keeps the 200-video cap and says `first 200 of N`; `c` opens the owner channel. Whether a Mix
(`RD…`) loads anonymously is not known: `scripts/owner/probe-playlist.py` records the replies first, and the Home Mix rows wait on that result.
Plan: `~/.claude-personal/plans/` (this session); steps are listed in [../status.md](../status.md) once they start.

## 2026-11-22 — Probe results (anonymous, `scripts/owner/probe-playlist.py`, run by the owner)

- **Normal playlist** (`browse VL<id>`): 200. The header is in `header.pageHeaderRenderer.content.pageHeaderViewModel` (owner "by Name" with the channel's `browseEndpoint`; a row "Playlist · 50 videos · 62,909 views"), the title and description in `metadata.playlistMetadataRenderer`, the thumbnail in `microformat`, "Updated 4 days ago" only in `sidebar.playlistSidebarRenderer`. The 50 videos are `lockupViewModel` and the existing parser reads them unchanged. `_playlist_info` now parses the header from that same reply; no second request.
- **Mix** (`browse VLRD<video>`): 200 with `alerts: "This playlist type is unviewable."` and nothing else. So a Mix cannot be a browse page. **`/next` with `videoId` and `playlistId=RD<video>` works anonymously**: 25 `playlistPanelVideoRenderer` rows, `isInfinite: true`, title "Mix - <video title>", owner "YouTube", no total. Supporting Mixes needs a second loader (a `/next` parser and its continuation) and an "endless" footer instead of `first 200 of N`. Not in the first cut: Mix rows stay hidden or open in the browser until that loader exists.
- **Watch Later** (`VLWL`): "The playlist does not exist." anonymously, as expected; it stays a History source.
- **Topic (`OLAK…`) playlists:** the search for one found none; still unprobed. **Private playlists:** unprobed (needs an id from the owner).
- Unviewable and missing playlists give an `alerts` reply with no `header`; the parser reports YouTube's own sentence and the page shows it.

## 2026-11-22 — Built: playlist page, Mixes, Home rows

- **Playlist page:** `ChannelScreen(playlist=row)`; header from the first page's `ChannelPage.info`; `o` opens the owner channel, `c` the channel of the highlighted video; tabs, sort and follow are hidden and answer with a reason. The owner id is parsed from the header, so the search rows need no owner field (the plan's step 2 was dropped).
- **Mixes work after all, but not through `browse`:** `next` with `{"playlistId": "RD<video>"}` returns 24 to 25 rows anonymously, and `next` with the last row's `videoId`, `playlistId`, `index` and `params` continues it (recorded 2026-11-22; the continuation repeats the last row and may repeat earlier ones, the list's id de-duplication absorbs that). `RDMM` ("My Mix") needs an account and shows "This Mix is not available without signing in." `fetch_mix_page` reads it; a Mix is endless, so the 200 cap ends it and the footer says `first 200 shown`.
- **Home:** `FeedCursor(playlists=True)` keeps playlist and Mix rows; Enter opens the page. Only Home: the other account feeds are lists of videos. Not seen against a signed-in Home (needs the owner's cookies).
- **Still open:** Topic (`OLAK…`) and private playlists were not probed; play all and save stop at 200; Watch Later and Liked stay out.

## 2026-11-27 — Playlist rows play in place; a video run is one mpv per video

`v` `a` `e` on a playlist row play or queue it; `>` `<` step. Owner request. Video chains one `WatchModal` per item, so the mpv window closes and reopens between videos. Rejected: one long-lived mpv fed by `loadfile` (a seamless window, but URL resolution, the separate audio stream, SponsorBlock and resume state would all have to be swapped inside a running player). The mpv window's keys report back through exit codes. No video run starts from inside the playlist page.
