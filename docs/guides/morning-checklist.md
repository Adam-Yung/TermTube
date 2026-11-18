# Live checks only a human can do

The tests never touch YouTube, a real browser profile, or a real terminal. These checks cover what they cannot. Each item names the doc that records the assumption. Anything that fails: note the screen and the key, then see the doc.

## Needs YouTube (and a signed-in browser where noted)

- [ ] **Home paging**: scroll past the first batch (80). Footer shows `loading 80 more…`, then the total. (`docs/decisions/feeds-and-paging.md`, `FeedCursor`)
- [ ] **History, YouTube side** (signed in): `Y` loads your YouTube history, `I` imports it. Check the titles and channels look right. The real `:ythis` entry fields are unknown.
- [ ] **Search filters**: `s` (sort) and `t` (type) on the Search tab return filtered results. Wrong params return unfiltered results, not an error. (`docs/decisions/ui.md`)
- [ ] **Channel page**: Videos continue past the first page. Shorts and Live tabs appear for a channel that has them and show rows. A channel playlist opens in place. The "Joined" line may be empty. (`docs/decisions/feeds-and-paging.md`)
- [ ] **Resume**: play a video, quit, play it again. It resumes. (real mpv)
- [ ] **`Q` queue** opens from each screen.
- [ ] **Cookie prewarm** (Settings, Account): on, then start the app. Home loads without a visible stall.
- [ ] **Errors in plain words**: with a signed-out browser, Home/Subscriptions say to sign in. Offline, the message says the network is down.

## Needs a human eye

- [ ] **Layout at 80x24, 100x30 and wide**: Library with the left rail, the Actions panel (no entry repeated from the bottom bar, none cut off), the new-playlist box centered like other dialogs.
- [ ] **Windows Terminal** looks right (CI covers behaviour only).
- [ ] **Delete in Library** asks first, then removes the file outright (no trash).
- [ ] **Playlists**: create, rename, add, remove, fuse; names with brackets or odd spaces.

## Decisions waiting for you

- No cross-process lock: two TermTube instances can overwrite each other's stores (`docs/decisions/concurrency.md`).
- Under 100 columns the channel page drops the info column.
- `Esc` on a Library list goes to the rail, but does nothing on History, Home or Subscriptions.
- `Z`, `F`, `Y`, `I` each work on one tab only.
- `home_revalidate` has no Settings row.
- Still cramped at 80x24 (Actions panel about 8 entries, list 40 wide).
- Your old watch history was lost when a test polluted `~/.config/TermTube/history.json`; restore from Time Machine if you have it (a backup of the config before the audit is at `~/.config/TermTube.backup-pre-audit-2026-11-17`).
- `audit-impl` is not merged into `main`. Merge it when the checks above pass.
