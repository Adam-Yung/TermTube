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

`s` and `t` on the Search tab pick sort and result type through the existing `SortModal` (now taking `options` and `title`; no second modal). The choice lives on the `SearchFrame`, so Backspace restores it with the results; a new query starts at relevance/all. The cache key is `query|sort|kind`. The request `params` blobs are protobuf: sort in field 1 (date 2, views 3), type in field 2.2 (video 1, channel 2, playlist 3). Single filters are the commonly documented values: `CAI=` date, `CAM=` views, `EgIQAQ==` video, `EgIQAg==` channel, `EgIQAw==` playlist **[verify live]**. Combined sort+type blobs (`CAISAhAB` ...) are the two messages joined, not seen working **[verify live]**. Nothing was called offline; a wrong value would return unfiltered results, not an error. Playlist rows from search do not open in the app (a remote playlist has no loader here): Enter says "press b". Result cap 200 by continuations as the user pages; an extension re-reads the earlier pages and skips them rather than keeping a cursor, because the cursor would need to survive the search stack. yt-dlp cannot filter, so it is the fallback for relevance/all only.

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

