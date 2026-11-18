from __future__ import annotations

from textual.events import Key

from src.entries import Entry
from src.tui.keymap import FOCUS_RECLAIM_KEYS
from src.tui.widgets.video_list import FilterBar, VideoListPanel


class ListNavMixin:
    """Cursor, page and focus handling for a screen that owns one ``VideoListPanel``.

    The screen sets ``_LIST_ID`` to the panel's selector, defines the hooks ``_on_page_shown`` (the user landed
    on another held page) and ``_on_past_last_page`` (a page that is not held was asked for; not here as a
    default: a no-op in this class would shadow the loader's), and may override ``action_tab_prev`` and
    ``action_tab_next``.
    """

    _LIST_ID: str

    def _list(self) -> VideoListPanel:
        return self.query_one(self._LIST_ID, VideoListPanel)

    def _selected_entry(self) -> Entry | None:
        return self._list().selected_entry

    def action_cursor_down(self) -> None:
        self._list().cursor_down()

    def action_cursor_up(self) -> None:
        self._list().cursor_up()

    def action_goto_start(self) -> None:
        panel = self._list()
        if panel.current_page != 1:
            panel.load_page(1)
        else:
            panel.cursor_first()

    def action_goto_end(self) -> None:
        panel = self._list()
        last = panel.total_pages
        if panel.current_page != last:
            panel.load_page(last, cursor="last")
            self._on_page_shown()
        else:
            panel.cursor_last()

    def action_page_prev(self) -> None:
        panel = self._list()
        if panel.can_go_prev():
            panel.load_page(panel.current_page - 1)

    def action_page_next(self) -> None:
        panel = self._list()
        if panel.is_loading:
            return
        if panel.can_go_next():
            panel.load_page(panel.current_page + 1)
            self._on_page_shown()
        else:
            self._on_past_last_page()

    def action_filter(self) -> None:
        if not self._list().open_filter():
            self._hint("Nothing to filter yet.", "information")

    def _close_filter_if_active(self) -> bool:
        """Esc/Backspace clear a kept filter before they go back. True when it did."""
        panel = self._list()
        if not panel.filter_active:
            return False
        panel.close_filter()
        return True

    def on_video_list_panel_page_change_requested(
        self, message: VideoListPanel.PageChangeRequested
    ) -> None:
        if message.direction > 0:
            self.action_page_next()
        else:
            self.action_page_prev()

    def on_key(self, event: Key) -> None:
        """Pull focus back to the list: DOM changes can leave it on the tab bar."""
        focused = self.app.focused
        owns_keys = isinstance(focused, FilterBar) or getattr(focused, "OWNS_NAV_KEYS", False)
        if event.key not in FOCUS_RECLAIM_KEYS or owns_keys:
            return
        try:
            panel = self._list()
        except Exception:
            return
        if not panel.list_has_focus():
            panel.focus_list()
