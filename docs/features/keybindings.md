# Keybindings

Defined in code in `src/tui/keymap.py` (main and channel screens), `src/tui/screens/watch_modal.py` (video player) and each modal's
`BINDINGS`. Shown to the user in `src/tui/screens/help_screen.py`, `src/tui/widgets/action_bar.py` and
`src/tui/screens/video_action_modal.py`. Change all of them together.

## Design rules

1. **hjkl move through whatever you are looking at.** `j`/`k` move the cursor down/up. `h`/`l` move along the other axis: pages in a list,
   time in the video player. A key never changes meaning with playback state.
2. **Shift widens the move.** `H`/`L` change tab (the next coarser unit than a page); in the video player they seek ±10 s.
   `g`/`G` go to the first/last item of the whole list, as in vim.
3. **Mnemonic letters for actions, lower case for the default, upper case for "ask me first".** `v` video, `a` audio, `V`/`A` pick the
   quality first. `d` download, `c` channel, `p` playlist, `y` yank the URL, `b` browser, `e` enqueue.
4. **Audio transport lives on keys that nothing else uses.** `Space` pause, `x` stop, `[`/`]` seek ±5 s, `{`/`}` ±10 s, `0`–`9` seek to
   0–90 %, `>` next track, `<` previous track. They work from any list because audio is background playback.
5. **One key, one action.** No key is "listen or seek" or "stop or subscribe".
   **A key that cannot act says why** (a short notice, at most once per 2 s): not a video, nothing playing, queue empty, already playing this track, live stream, already downloaded, no URL. **Keys that cannot work together are refused with a hint, not run.** While audio plays, `v` / `V` do nothing but say so (video and audio would overlap); stop audio with `x` first. Open decisions: `docs/plans/2026-11-15-key-conflicts-PLAN.md`.
6. **`D` always means "remove this from where I am looking"** and asks once, in the action bar, saying what it will remove. `y` confirms;
   every other key cancels and does nothing else. A tab that cannot remove says why. `u` undoes the last removal for 30 s (entries only; files are never undone).
   `Q` (queue view) is reserved for a later phase and unbound today.
7. `Esc` and `Backspace` go back (out of the channel page; on the Search tab, to the previous search at its page and row; on the Library, History and Subscriptions tabs, from the list to the side list). `q` quits the app, or stops the video player. Arrow keys mirror `h`/`j`/`k`/`l`.
8. **Library, History and Subscriptions have two panes, and `Tab` moves between them.** The left side list holds the tab's sources: Library collections and playlists; TermTube history, YouTube history and Watch Later; Subscribed and Following. With the side list focused `j`/`k`/`g`/`G` walk its entries, `Enter` shows one (and focuses the list), `l`/`→` returns to the list without choosing, and `h`/`←` on the first page of the list moves to the rail. Keys that act on a row (`d` `p` `c` ...) do nothing while the rail has focus, except `v` `a` `e` on a playlist, which play or queue it; the playlist keys (`R` `D` `P` `S` `E`) act on the playlist under the rail cursor. `D` still means "remove the thing I am on": a row in the list, a playlist in the rail.

## Map

| Key | Main / channel list | Video player |
|---|---|---|
| `j` `k` | cursor down / up | |
| `h` `l` `←` `→` | previous / next page | seek −5 s / +5 s |
| `H` `L` | previous / next tab | seek −10 s / +10 s |
| `g` `G` | first / last item of the list | |
| `Enter` | action menu: the row actions below that apply to the row (the menu and the Actions panel are built from `keymap.ROW_ACTIONS`); the panel leaves out the footer keys `/` `r` `,` `?` `q` and lists only what applies to the current tab, focus and row (no download on a playlist row, no `D` on Home, rail tools while the rail has focus; entries that do not fit end in `…`) | |
| `v` `V` | watch / choose quality (refused while audio plays) | |
| `v` `a` `e` on a playlist or Mix row, or a rail playlist | play it as video, one after another / play it as audio (replaces the track and the queue) / add it to the queue; `V` `A` have no playlist form | |
| `>` `<` in a playlist video run | | next / previous video (also in the mpv window); `q`, `Esc` or closing the window ends the run |
| `a` `A` | play audio / choose quality (replaces the current track) | |
| `e` | add audio to the queue | |
| `>` `<` | skip to the next queued track / back to the track played before | |
| `Space` | pause audio | pause |
| `x` | stop audio, clear queue | |
| `[` `]` `{` `}` | audio seek ∓5 s / ∓10 s | same keys, same distances |
| `0`–`9` | audio seek to 0–90 % | seek to 0–90 % |
| `d` `c` `p` `y` `b` | download / channel / playlist / copy URL / browser | |
| `f` | filter the loaded list as you type, across all pages (`Enter` keeps it, `Esc` clears it); also on the channel page. On the Library tab it also takes tokens: `type:audio`, `dur:<10m`, `by:"name"`, `year:2024`, `pl:name`, `dl:yes` | |
| `m` `M` | mark the row and move down / mark the page (`●`; marks survive paging, clear on a view change) | |
| `D` `u` | remove the row or the marked rows (History, Library and playlists; on the rail, the playlist under the cursor) after `y` / `N` / undo the last removal | |
| `/` `r` `,` `?` `Ctrl+D` `q` | search / refresh / settings / help / debug log / quit | `q` `Esc` stop |
| `F1`–`F6` `` ` `` | jump to a tab (Help is `F6`) / tab picker | |
| `Tab` | Library, History, Subscriptions: move focus between the side list and the list (a hint elsewhere) | |
| `n` `R` | Library tab: new playlist / rename the playlist under the rail cursor or the open one (a hint elsewhere) | |
| `J` `K` | inside a playlist: move the video down / up, saved at once (a hint elsewhere) | |
| `P` `S` `E` | play / shuffle / queue the open or highlighted playlist as audio (a hint elsewhere) | |
| `I` | History tab, YouTube history source: imports the rows (or the marked ones) into local history (a hint elsewhere) | |
| `s` `t` | Search tab: sort (relevance / date / views) / result type (all / video / channel / playlist); `s` on the local History tab: recent / most watched / longest watched (a hint elsewhere) | |
| `Q` | open the audio queue (any screen with the audio bar): `j` `k` move, `J` `K` reorder, `D` remove, `u` undo, `Enter` play now, `Esc` close; "Nothing playing." when idle | |
| `s` `r` `i` `Esc` | channel page only: sort / reload / fold or unfold the description (shown in full by default) / back | |
| `B` | channel page: follow or unfollow the channel locally (`channels.json`, works with `browser: none`) | |
| `o` | playlist page (a playlist opened from Search or Home): open the channel that owns the playlist; `s`, `B`, `H` `L` and the tab menu answer "A playlist has no tabs, sort or follow." there | |
| `Z` | Home tab: show or hide the videos already played (the footer says `N hidden`, or `played shown`); a hint on other tabs | |
| `F` | Subscriptions tab: the local Following list (`Enter` opens a channel, `Esc` returns); a hint on other tabs | |
| `P` `E` `S` | channel page, inside a playlist (`Enter` on a playlist row opens it): play all / add all to the queue / save as a local playlist | |
| `/` `,` `?` `q` | work on the channel page too: `/` and `q` leave it first (search results and quit belong to the main screen) | |
| `↑` `↓` `Enter` `Ctrl+D` | search prompt only: walk the earlier searches / search the highlighted one / forget it | |

## What changed from the first keymap (2026-11-15)

| Before | Problem | Now |
|---|---|---|
| `l` listen, but seek +5 s while audio plays | key meaning depended on state; `l` is a motion key | `a` audio; `l` next page |
| `L` listen quality / seek +10 s | same | `A`; `L` next tab |
| `h` `H` seek back (audio only) | motion keys did nothing without audio | `h` previous page, `H` previous tab |
| `w` / `W` watch | arbitrary letter | `v` / `V` |
| `s` stop audio, or "subscribe" | two unrelated actions; "subscribe" only opened a browser tab | `x` stops audio; subscribe removed (`b` opens the page) |
| `s` sort, or stop (channel page) | same overload | `s` sort only |
| `[` `]` pages | free once `h`/`l` page | audio seek |
| `g` `G` first / last *page* | not vim semantics | first / last item of the list |
| Help listed `a` download audio | never implemented | `d` opens the picker for both |
| `e` enqueue only while playing | silent no-op otherwise | starts playback when idle |
| Channel page lacked `e`, `>`, `x`, `V` | copy of the main screen's keys, drifted | same table via `keymap.py` |

Not changed: `F1`–`F6` and `` ` `` (F-keys need `fn` on macOS; the picker covers that), `d`/`c`/`y`/`p`/`b`, `/`, `r`, `,`, `?`.
