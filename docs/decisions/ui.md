# UI decisions

## 2026-11-16 — Notifications styled like the dialogs, top right

Textual's default toast is a blue-grey slab with green, orange and magenta bars, the only part of the UI outside the black and red palette, and it sat bottom right on top of the Actions and Now Playing bar. Toasts now use the dialog background (`#141414`), the dialog border (`#333333`), and the list highlight's thick left bar: the theme accent for information, yellow for warning, and a full red border with pink text for errors. They are compact (`width: auto`, 24 to 50 cells, one row of padding less) and the rack docks top right under the tab bar. Rules live in `theme.tcss` (base block plus one `Toast.-information` line per theme). Rejected: custom toast widgets or an `App.notify` wrapper that adds icons; CSS alone was enough and messages keep their own glyphs.

## 2026-11-17 — Playlist `create` refuses an existing name

`playlist.create` used to reset a playlist of the same name to empty, so typing an existing name in the modal wiped it. It now returns `False` and writes nothing; the modal warns and adds nothing. The modal also pins the entry it holds (fat fields stripped) instead of relying on the video still being in the metadata cache, which is the stopgap for rows that showed a bare id; the full fix is the playlist v2 model (Phase 5).

## 2026-11-17 — List tools live in the shared list engine

Filter (`f`), marks (`m`/`M`), remove (`D`) and undo (`u`) are implemented once, in `VideoListPanel` plus `ListToolsMixin`, not per tab. A tab opts in to `D` by declaring a `Removal` in `MainScreen._removals()`; History is the first. Choices: the filter is substring-with-ranking over title and uploader/channel (own scorer, `src/fuzzy.py`, no dependency) and applies to every loaded page; the remove question is one inline line in the action bar where `y` confirms and any other key cancels without acting; undo keeps one removal for 30 s and covers entries only. History day headers are display-only rows inside the `ListView` (never in the page data), so paging and counts are unchanged; they are hidden while a filter is active. Keys `f m M D u` were free in every screen and modal; `J` `K` `Q` stay unbound until their phases.

## 2026-11-17 — Search stack: rows by id, breadcrumb shows depth

The Search tab keeps a stack of up to 20 searches (`src/search_stack.py`). A frame stores the page and the id of the highlighted row, not its index, so the restore survives re-paging. Backspace/Esc pops only when the tab-level `_nav_stack` (playlist back) is empty, so the other meanings are unchanged. The breadcrumb reads `‹ N searches · Backspace: back to “prev”` instead of the plan's `‹ 2 of 5 ›`: a pure stack has no forward half, so "n of m" would always read n of n.

## 2026-11-17 — Search suggestions on by default, opt-out

Typing in the search prompt asks `suggestqueries.google.com` (anonymous, no cookies, no account headers, verified TLS) for suggestions after a 250 ms pause, 2 or more characters. **Privacy:** the partial text reaches Google before the user submits anything, which no other part of the app does. The owner chose on-by-default (plan question E3) with an opt-out: `search_suggestions: false` or the Settings toggle, which carries a one-line note saying so. Mitigations: nothing but the text and a generic User-Agent is sent, one request per pause (an answer for older text is dropped), 2 s timeout, 16 KB cap, errors silent. Rejected: opt-in (nobody would find it), a local-only index (no new queries).

## 2026-11-17 — Search sort and type: InnerTube `params`, filters belong to the search frame

`s` and `t` on the Search tab pick sort and result type through the existing `SortModal` (now taking `options` and `title`; no second modal). The choice lives on the `SearchFrame`, so Backspace restores it with the results; a new query starts at relevance/all. The cache key is `query|sort|kind`. The request `params` blobs are protobuf: sort in field 1 (date 2, views 3), type in field 2.2 (video 1, channel 2, playlist 3). Single filters are the commonly documented values: `CAI=` date, `CAM=` views, `EgIQAQ==` video, `EgIQAg==` channel, `EgIQAw==` playlist; checked live on 2026-11-18: each type filter returns only that type, and view-count sort returns rows in descending views. Combined sort+type blobs (`CAISAhAB` ...) work too. Date sort changes the ranking toward recent uploads but is not strictly newest first (YouTube's own behaviour for the anonymous API; a quiet topic shows old videos first). Nothing was called offline; a wrong value would return unfiltered results, not an error. Playlist rows from search do not open in the app (a remote playlist has no loader here): Enter says "press b". Result cap 200 by continuations as the user pages; an extension re-reads the earlier pages and skips them rather than keeping a cursor, because the cursor would need to survive the search stack. yt-dlp cannot filter, so it is the fallback for relevance/all only.

## 2026-11-17 - Playlists v2 and management keys

Playlists are addressed by stable id (`pl_xxxx`), not name, so rename and the `playlist:<id>` tab id cannot break; names are unique case-insensitively. Items are history-style slim snapshots so a row never shows a bare id; v1 items migrate with an empty title that the cache fills on first open. v1 file backed up once as `playlists.json.v1`; duplicate names that differ by case become `Name (2)`. Keys: `n` new, `R` rename, `J`/`K` move, `P`/`S`/`E` play / shuffle / queue all (lower-case `p`, `s`, `e` were taken by the playlist dialog, search sort and row enqueue). Each is declared once in `keymap.PLAYLIST_TOOLS` and says what to open when used outside the Playlists tab, as `s`/`t` do on Search. Play-all replaces the audio queue; queue-all appends and skips tracks already queued. The playlist dialog selects with `Space` and applies with `Enter` (with nothing selected `Enter` still flips the highlighted row). Names are asked in a small `NameModal`, not inline in the bar: the action bar has no text input and the dialog reuses the playlist styling.

## 2026-11-17 - One Library tab with a left rail (P5.3, P5.4)

The Playlists tab is gone; F-keys are `F1` Home, `F2` Subscriptions, `F3` Search, `F4` History, `F5` Library, `F6` Help (the picker is 1-6). The Library tab has a
rail (All downloads, Videos, Audio, playlists, + New playlist). Focus: `Tab` toggles rail and list (no key changes meaning with state; `Tab` did nothing else
on this screen). In the rail `j`/`k`/`g`/`G` move, `Enter` shows the entry and focuses the list, `l`/`Right` returns to the list without choosing. `Esc` and
`Backspace` from the list go to the rail: nothing else used them on this tab once the playlist drill-down (`_open_playlist`, `_nav_stack`) was removed.
`D` on a rail entry deletes that playlist (the thing under the cursor), in the list it removes the row. Row actions are inert while the rail has focus.
`h`/`l` stay page keys: using `h` on page 1 to enter the rail would have given `h` a state-dependent meaning.

Narrow terminals (under 100 columns) collapse the rail into one docked line instead of overflowing; the same keys cycle its entries.

The filter hook is `VideoListPanel.set_matcher`; Library collections and playlists use `library_query.rank`, everything else keeps `fuzzy.rank`. Tokens
that do not parse stay free text so a typo never raises. A search across History, Library and playlists together stays out of scope.

## 2026-11-17 — History sources: `Y` switches, `I` imports

The History tab holds sources: Local (`history`), YouTube history (`history:yt`) and Watch Later (`history:wl`), the last two read-only from the account (P6.3 chose the History tab's source switch over a separate account-feeds picker: no new tab or modal). `Y` cycles them; `[` `]` are audio seek,
`Tab` belongs to the Library rail, and `Y` was free and reads as "YouTube". `I` imports the YouTube rows into the local history (a capital next to
nothing else, only active on that source). F4 returns to the last source used. `D` on a YouTube source only explains it cannot remove (the owner
made YouTube history read-only), and says to open youtube.com/feed/history instead, because `b` opens the selected video as everywhere. YouTube
rows carry no timestamps (the flat feed gives none that were verified): no day headers, a `YT` badge. Imported rows keep `watched_at=None` and sort
after dated ones (`docs/code/src/history.py.md`).

## 2026-11-17 — `playlist.transfer` removed

It had no UI and duplicated what the keys already do: `p` adds the selected video to other playlists and `D` removes it from the current one. A move is those two steps.

## 2026-11-18 — Layout rules: dialogs, the Enter menu, the Actions panel

The owner found modals off-center (the new-playlist prompt), a list-heavy dialog pushing its hint off the box, and shortcut entries cut off in the Actions panel and repeated from the footer. The rules, enforced by `src/tests/tui/test_layout_audit.py` (every modal at 80x24, 100x30, 120x40, 160x50 and 60x20):

- **One centering rule.** `ModalScreen { align: center middle; }` in `theme.tcss`; no per-modal `align`. Every dialog box has `class="dialog"` (sizes to its content, at most 90% of the screen high and wide, `min-width: 36`, scrolls itself when the screen is smaller than its content). Only width, background and border colour differ per dialog, set by id.
- **Lists scroll, not the frame.** A list in a dialog has `class="dialog-list"`: `height: auto; max-height: 50vh`. The title and hint stay in the box at any height; the list scrolls past half the screen. `1fr` or a fixed row cap cannot do this in an auto-height box (a fixed cap overflowed at 24 rows).
- **Minimum size.** Dialogs are meant for 80x24 and up. At 60x20 they stay on screen and centered, and the box scrolls its own content; nothing is drawn outside it.
- **The menu and the panel have one source.** `keymap.ROW_ACTIONS` lists the actions on the highlighted row; the Enter menu and the Actions panel both read it, and the key letter comes from the binding (`keymap.key_of`). The menu hides what would only answer with a hint for the row (missing file, live stream, already downloaded, the channel page's own channel).
- **The Actions panel never repeats the footer.** `/` search, `r` refresh, `,` settings, `?` help and `q` quit are footer keys and are not in the panel (a test compares them). The panel picks its column count from its width and grows to the rows it needs.
- `#thumbnail-area` is at most half the detail panel so the info and the panel fit on a 30-row terminal.


## 2026-11-18 — Main-screen layout rules (UI audit, part B)

The owner found part of the Library list pushed off screen next to the new rail. Cause: the rail was 26 cells and the list and detail panel were `45%` and `55%` of the whole row, so the three summed to more than the screen and the detail panel fell off the right edge (100x30, 120x40, 160x50). `src/tests/tui/test_screen_layout_audit.py` now opens every tab, every History source, every Library collection, the playlist view, the Following view and the channel page (Videos, Playlists, Shorts, Live, expanded description) at 80x24, 100x30, 120x40 and 160x50 with fake data.

- **Widths are fractions of what is left.** Rail `24`, list `9fr` (min 40), detail panel `11fr` (min 30). Under 100 columns the rail collapses to the one-line selector, so the list never drops below 40 cells at any size.
- **Breakpoints, not Python checks.** `App.HORIZONTAL_BREAKPOINTS` (`src/tui/layout.py`) puts `-narrow` / `-wide` on every screen; the stylesheet keys on it. Under 100 columns tabs use `padding: 0 1` (all six fit 80 columns; at `0 3` Library and Help were off screen) and the channel page hides its info column (22% of 80 columns left 17 cells; the list and detail panel get 55% / 45%). Judgment call for the owner: the channel info (subscribers, description) is not reachable under 100 columns.
- **Detail panel vertical budget.** Video info keeps 6 rows first (it showed 2 at 80x24). Then the Actions panel (at most 5 grid rows, ending in a `…` cell when entries do not fit). The thumbnail gets what is left, at most 25 rows and half the panel, and is hidden under 6 rows. At 80x24 with the one-line rail it is hidden.
- **Breadcrumbs are one line** with an ellipsis (the Following and YouTube-history breadcrumbs wrapped to two lines and were cut).
- **The one-line rail fits its width**: its `▸ i/n` position was 3 cells too wide and cut.

## 2026-11-18 — The Actions panel shows what applies (UI audit, part B)

The panel listed all 21 tools of every tab (7 rows at 100x30). The screen now answers `panel_hints()`: Enter plus the row actions that apply to the highlighted row (`ROW_ACTIONS` minus the Enter menu's hidden set; a playlist or channel row only gets copy URL and browser, and a channel row `⏎ Open channel`), then the tools that apply to the tab and focus (`keymap.PANEL_TOOLS`: `f` filter, `m` `D` where the tab can remove, `u` while an undo is open, `Y` and `I` on History, `Z` on Home, `F` on Subscriptions, `s` `t` on Search, `n` in Library, `R` `J K` `P` `S` `E` on a playlist; with the rail focused only the rail's tools; the channel page lists follow and, inside a playlist, play all, queue all and save). The `HAS_*` class flags are gone. The grid shows at most 5 rows and ends in `…` when entries do not fit; `?` lists every key.

## 2026-11-18 — Consistency pass (UI audit, part B)

- **Empty and failed lists speak in the list, not the breadcrumb.** `set_empty_message` and `set_error_message` showed their text in the one-line breadcrumb, which cut "No channels followed here yet. Press B on a channel page." at 80 columns and the multi-line "Feed loading failed" notice to its first line. They now use a wrapping `#list-message` that replaces the list until rows or the loading spinner come back. History and Library say what to do instead of "No items".
- **Notice wording.** A message that explains why a key did nothing (`_hint`, "Already playing this track.", "Already in the queue.", `Playlist "x" already exists.`) is a sentence with a period. A success notice is a fragment without one ("URL copied to clipboard", "Added to ..."). The terms are playlist (never "list") in labels: the panel says `New playlist` and `Save playlist`; removed (undoable) versus deleted (files gone, no undo).
- **Panel keys that exist.** `s` on local History opens the sort picker, so the panel lists it there. `HAS_*` flags were dead after the panel moved to `panel_hints`.
- **Key-consistency tests.** `test_help_matches_keymap.py`: every row action and panel tool key is in the help screen, the footer keys are, and F1..F6 match the tab count. `test_focus_after_modal.py`: Esc from each dialog returns focus to the list with the cursor kept.
- **Judgment calls left to the owner** (nothing was changed): the channel page hides its info column under 100 columns; Home, Subscriptions and Search answer `D` with a hint instead of hiding the key; `Esc` on the Library list moves to the rail (it never leaves the tab), while `Esc` on History, Home and Subscriptions does nothing; `Z` and `F` are single capital letters that only work on one tab each, like `Y` and `I`.

## 2026-11-18 — Wiring bug hunt: no hook defaults in mixins, tests read the MRO

- **A mixin does not ship a default for a hook another class provides.** `_removals`, `_after_removal` and `_crumbs` had empty defaults that only worked because the host or `LibraryRailMixin` sat earlier in the MRO. They are gone; the mixin docstrings say who provides them. The two defaults that stay (`_worker_start`, `_worker_end` in `DetailFocusMixin`, and `ChannelScreen._on_page_shown`) are listed with the reason in `test_mixin_wiring.py`.
- **Overrides are listed.** `test_mixin_wiring.py` holds, per screen, every name defined by more than one class in the MRO and the class that must win. A new duplicate fails until a person adds it with the winner.
- **Textual runs every class's `on_<message>` handler**, so two mixins handling the same message do not shadow each other (until one calls `prevent_default`). The only duplicate is `on_key`, listed.
- **`_pending_show` is reset by `_start_view`.** A waiting extension from the old view left it set; the new view's first background extension then jumped to its next page.
- **`theme.tcss` rules for `#list-loading` and `Scrollbar`** matched nothing (no such widget id, no such Textual type) and were removed; `test_theme_wiring.py` fails on a selector that names nothing composed.

## 2026-11-18 — List messages escape their text; debug logs are redacted
`VideoListPanel.set_error_message` / `set_empty_message` put text into markup. A raw exception text from yt-dlp (`[youtube] id: ...`, `[/x]`) raised `MarkupError` in the worker. They now escape (errors also cut at 400 characters). The `--debug` log passes every record through `logger.redact` so signed URLs and credentials never reach the file or the debug window.

## 2026-11-18 — `escape_markup` handles backslashes; every user text in a notice or log is escaped
A text ending in a backslash (or with one before `[`) escaped the closing tag that followed it: the tag showed as text and the style ran on (`[/y] \` in an error). Markup cannot spell a literal backslash there, so `escape_markup` puts a zero-width space after it. Notices and log lines that embed titles, playlist or channel names, URLs or error text (audio, download modal, playlist modal, channel follow, feed loader) now go through it too. `test_loader_errors.py` injects every typed error and a raw exception into each list loader.

## 2026-11-18 — `set_breadcrumb` takes plain text and escapes it
Search queries and playlist names went into the breadcrumb markup unescaped (`[/x]` in a query or a playlist name raised `MarkupError` on render). `VideoListPanel.set_breadcrumb` now escapes its argument; the channel screen no longer escapes first. `test_scale_edge.py` holds the 5000-row budget test (ranking 5000 rows is about 10 ms, so no cache of haystacks is needed), the odd-name playlist cases, garbage filter queries and hostile text in rows, notices, breadcrumbs and the detail panel.

## 2026-11-18 — History and Subscriptions use the Library's side list; `Y` and `F` are gone
The History tab had a `Y` key that cycled its sources, and Subscriptions had `F` for the Following list; Library had a rail. All three now share the rail: one entry per source (History: TermTube history, YouTube history, Watch Later; Subscriptions: Subscribed, Following), `Tab` moves focus between rail and list, `Enter` on an entry loads it. Each tab opens on its first entry. Rejected: keeping `Y` / `F` as aliases (two ways to do one thing, and the rail shows what sources exist). `Esc` / `Backspace` from the list now goes to the rail on all three tabs, so `Esc` no longer leaves Following (pick Subscribed). The widget and mixin keep their `Library` names; a rename is mechanical and not done yet.
