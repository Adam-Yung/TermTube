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
   0–90 %, `>` next track. They work from any list because audio is background playback.
5. **One key, one action.** No key is "listen or seek" or "stop or subscribe".
   **A key that cannot act says why** (a short notice, at most once per 2 s): not a video, nothing playing, queue empty, already playing this track, live stream, already downloaded, no URL. **Keys that cannot work together are refused with a hint, not run.** While audio plays, `v` / `V` do nothing but say so (video and audio would overlap); stop audio with `x` first. Open decisions: `docs/plans/2026-11-15-key-conflicts-PLAN.md`.
6. **`D` always means "remove this from where I am looking"** and asks once, in the action bar, saying what it will remove. `y` confirms;
   every other key cancels and does nothing else. A tab that cannot remove says why. `u` undoes the last removal for 30 s (entries only; files are never undone).
   `J` `K` (move in an ordered list) and `Q` (queue view) are reserved for later phases and unbound today.
7. `Esc` and `Backspace` go back (out of a playlist or channel; on the Search tab, to the previous search at its page and row). `q` quits the app, or stops the video player. Arrow keys mirror `h`/`j`/`k`/`l`.

## Map

| Key | Main / channel list | Video player |
|---|---|---|
| `j` `k` | cursor down / up | |
| `h` `l` `←` `→` | previous / next page | seek −5 s / +5 s |
| `H` `L` | previous / next tab | seek −10 s / +10 s |
| `g` `G` | first / last item of the list | |
| `Enter` | action menu | |
| `v` `V` | watch / choose quality (refused while audio plays) | |
| `a` `A` | play audio / choose quality (replaces the current track) | |
| `e` | add audio to the queue | |
| `>` | skip to the next queued track | |
| `Space` | pause audio | pause |
| `x` | stop audio, clear queue | |
| `[` `]` `{` `}` | audio seek ∓5 s / ∓10 s | same keys, same distances |
| `0`–`9` | audio seek to 0–90 % | seek to 0–90 % |
| `d` `c` `p` `y` `b` | download / channel / playlist / copy URL / browser | |
| `f` | filter the loaded list as you type, across all pages (`Enter` keeps it, `Esc` clears it); also on the channel page | |
| `m` `M` | mark the row and move down / mark the page (`●`; marks survive paging, clear on a view change) | |
| `D` `u` | remove the row or the marked rows (History only so far) after `y` / `N` / undo the last removal | |
| `/` `r` `,` `?` `Ctrl+D` `q` | search / refresh / settings / help / debug log / quit | `q` `Esc` stop |
| `F1`–`F7` `` ` `` | jump to a tab / tab picker | |
| `s` `t` | Search tab: sort (relevance / date / views) / result type (all / video / channel / playlist); a hint elsewhere | |
| `s` `r` `Esc` | channel page only: sort / reload / back | |
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

Not changed: `F1`–`F7` and `` ` `` (F-keys need `fn` on macOS; the picker covers that), `d`/`c`/`y`/`p`/`b`, `/`, `r`, `,`, `?`.
