# UI decisions

## 2026-11-16 — Notifications styled like the dialogs, top right

Textual's default toast is a blue-grey slab with green, orange and magenta bars, the only part of the UI outside the black and red palette, and it sat bottom right on top of the Actions and Now Playing bar. Toasts now use the dialog background (`#141414`), the dialog border (`#333333`), and the list highlight's thick left bar: the theme accent for information, yellow for warning, and a full red border with pink text for errors. They are compact (`width: auto`, 24 to 50 cells, one row of padding less) and the rack docks top right under the tab bar. Rules live in `theme.tcss` (base block plus one `Toast.-information` line per theme). Rejected: custom toast widgets or an `App.notify` wrapper that adds icons; CSS alone was enough and messages keep their own glyphs.
