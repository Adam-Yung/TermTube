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
