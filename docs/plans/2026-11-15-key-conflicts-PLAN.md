# Key conflicts

Status 2026-11-16: the owner approved the added notices on condition that toasts match the TUI (done: `docs/decisions/ui.md`). **Done:** K1, K2, K4, K5, K7, K8, K9, K10, K13. K9 refuses only when a video and its audio both exist. **Next:** K3, K6, K11, K12. K14 stays as is.

Found by reading `src/tui/keymap.py` and the action methods, and by driving the real app in tmux (marked **seen**). K1 is done. For each
other item the proposal is mine; say keep, change or skip. Rule of thumb used: a key either does its job or says why it did nothing.

| # | Situation | What happens now | Proposal |
|---|---|---|---|
| K1 | `v` / `V` (and the menu's Watch entries) while audio plays | **Done.** Refused with "Audio is playing. Stop it with x before watching video."; the Enter menu hides both entries | none |
| K2 | `a` / `A` on the track that is already playing (**seen**) | The track restarts from 0:00 ("Buffering…") | No-op with "Already playing". `A` (quality) keeps working, since it can change the format |
| K3 | Channel page: `?` `,` `/` `q` (**seen**) | Nothing happens, though `docs/features/keybindings.md` lists them for the "main / channel list"; the footer shows only `esc s r` | Bind `q` (quit), `?` (help), `,` (settings) and `/` (search, then return to the main screen with the results) on the channel screen; show them in its footer |
| K4 | Transport keys with nothing playing: `Space` `x` `>` `[` `]` `{` `}` `0`–`9` | Silent no-ops | `Space`, `x`, `>`: show "Nothing playing" once; the rest stay silent (they are held-key friendly) |
| K5 | `>` while playing with an empty queue | Silent | "Queue is empty" |
| K6 | `e` with nothing playing | Starts playback; but the Enter menu hides "Add to queue" in that state, so the key and the menu disagree | Show "Add to queue" in the menu always; label it "Play next in queue" when idle |
| K7 | Video and audio keys on rows that are not videos (channel rows on Subscriptions, playlist rows): `v V a A e d p` | Silent no-ops; `y` says "No URL available", `b` is silent | One hint for all: "Not a video". `b` / `y` on a playlist or channel row open or copy that page's URL |
| K8 | `d` (download) on a live stream (`is_live`) | Not tested; nothing in the code stops it, so it probably starts a download of an unfinished stream. Esc cancels it, but nothing warns | Refuse with "Live stream: cannot download" |
| K9 | `d` on a Library row (already a local file) | Downloads the same video again | Refuse with "Already downloaded", or offer "audio only" if only the video exists |
| K10 | `s` (sort) on the channel Playlists tab; `s` → "Most viewed" on Videos | Playlists: silent. Most viewed: switches to the yt-dlp path (several seconds, no hint) | Playlists: "Playlists have no sort". Most viewed: show "Loading from yt-dlp (slower)…" |
| K11 | A modal is open (download, search, settings, quality, action menu) | Every audio key is blocked; you cannot pause or stop audio during a download | Keep (modal focus is the point), but add `Space` and `x` pass-through to `DownloadModal` only, since a download is long |
| K12 | Quit (`q`) while audio plays or a queue exists | Audio stops and the queue is lost without a word | Keep; mention "queue not saved" in the help screen |
| K13 | `c` on the channel page | Silent no-op (menu hides it) | Notify "Already on this channel" |
| K14 | `r` (refresh) on the Search tab, Library, History | Reloads the same list (Search is cache-first, so it may return the same results) | Keep |

Out of scope here: keys that change meaning between screens by design (`q` stops the video player, quits elsewhere; `h`/`l` page in lists
and seek in the video player).
