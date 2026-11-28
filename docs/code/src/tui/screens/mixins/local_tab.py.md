# src/tui/screens/mixins/local_tab.py

The Local tab (`F6`) on `MainScreen`: one folder of the disk in the shared list. Decision: [../../../../../decisions/local-files.md](../../../../../decisions/local-files.md).

- **Loading.** `ListSourcesMixin._source_loader` maps `local` to `_load_local`, which runs on the `feed_loader` thread, so a new tab
  or folder cancels it through `_feed_session` (the listing also polls it per entry). `_show_local` runs on the UI thread and puts the
  cursor on `_local_focus`: going up lands on the folder just left.
- **Navigation.** `MainScreen._activate_entry` sends folder rows to `_open_folder`; `action_nav_back` (Backspace, Esc) calls `_local_up`, which goes up from `_local_dir`, not from the rows on screen (those still show the previous folder while the next loads, so a second quick Backspace would be lost).
  The folder lives in `_local_dir` for the session; `r` re-reads it.
- **Removal.** `_local_removal` is the tab's `Removal`: permanent; folder rows never reach it (`ListToolsMixin._delete_targets`); `reload` returns the rows in memory minus the deleted ones, so `D` never rescans a slow disk on the UI thread.
- Row actions that need YouTube are hidden or answer with a reason in `ItemActionsMixin`; folder rows play their files through
  `PlaylistRowsMixin._playlist_source`.
