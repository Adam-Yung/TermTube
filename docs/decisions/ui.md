# UI decisions

## 2026-11-16 — Notifications styled like the dialogs, top right

Textual's default toast is a blue-grey slab with green, orange and magenta bars, the only part of the UI outside the black and red palette, and it sat bottom right on top of the Actions and Now Playing bar. Toasts now use the dialog background (`#141414`), the dialog border (`#333333`), and the list highlight's thick left bar: the theme accent for information, yellow for warning, and a full red border with pink text for errors. They are compact (`width: auto`, 24 to 50 cells, one row of padding less) and the rack docks top right under the tab bar. Rules live in `theme.tcss` (base block plus one `Toast.-information` line per theme). Rejected: custom toast widgets or an `App.notify` wrapper that adds icons; CSS alone was enough and messages keep their own glyphs.

## 2026-11-17 — Playlist `create` refuses an existing name

`playlist.create` used to reset a playlist of the same name to empty, so typing an existing name in the modal wiped it. It now returns `False` and writes nothing; the modal warns and adds nothing. The modal also pins the entry it holds (fat fields stripped) instead of relying on the video still being in the metadata cache, which is the stopgap for rows that showed a bare id; the full fix is the playlist v2 model (Phase 5).

## 2026-11-17 — List tools live in the shared list engine

Filter (`f`), marks (`m`/`M`), remove (`D`) and undo (`u`) are implemented once, in `VideoListPanel` plus `ListToolsMixin`, not per tab. A tab opts in to `D` by declaring a `Removal` in `MainScreen._removals()`; History is the first. Choices: the filter is substring-with-ranking over title and uploader/channel (own scorer, `src/fuzzy.py`, no dependency) and applies to every loaded page; the remove question is one inline line in the action bar where `y` confirms and any other key cancels without acting; undo keeps one removal for 30 s and covers entries only. History day headers are display-only rows inside the `ListView` (never in the page data), so paging and counts are unchanged; they are hidden while a filter is active. Keys `f m M D u` were free in every screen and modal; `J` `K` `Q` stay unbound until their phases.
