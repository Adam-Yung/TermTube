"""The list's cursor and what it tells the screen: keyboard moves, clicks and page-indicator clicks."""

from __future__ import annotations

from textual.widgets import ListView

from src.entries import Entry
from src.tui.widgets.page_indicator import PageIndicator
from src.tui.widgets.video_rows import VideoListItem, _ItemClicked, _ItemDoubleClicked


class ListCursorMixin:
    """The highlighted row of ``VideoListPanel`` and the messages it posts.

    Needs ``_lv``, ``can_go_prev``, ``can_go_next``, ``Selected``, ``Activated``, ``PageChangeRequested``,
    ``post_message`` and ``app`` from the panel.
    """

    @property
    def selected_entry(self) -> Entry | None:
        if self._lv.index is None:
            return None
        try:
            child = self._lv.highlighted_child
            if isinstance(child, VideoListItem):
                return child.entry
        except Exception:
            pass
        return None

    def focus_list(self) -> None:
        self._lv.focus()

    def list_has_focus(self) -> bool:
        return self.app.focused is self._lv

    def cursor_down(self) -> None:
        self._lv.action_cursor_down()

    def cursor_up(self) -> None:
        self._lv.action_cursor_up()

    def cursor_first(self) -> None:
        for i, child in enumerate(self._lv.children):
            if isinstance(child, VideoListItem):
                self._lv.index = i
                return

    def cursor_last(self) -> None:
        if len(self._lv):
            self._lv.index = len(self._lv) - 1

    def on__item_clicked(self, msg: _ItemClicked) -> None:
        highlighted = self._lv.highlighted_child
        already_focused = (
            isinstance(highlighted, VideoListItem)
            and highlighted.entry.get("id") == msg.entry.get("id")
        )
        if already_focused:
            self.post_message(self.Activated(msg.entry))
        else:
            for i, child in enumerate(self._lv.children):
                if isinstance(child, VideoListItem) and child.entry.get("id") == msg.entry.get("id"):
                    self._lv.index = i
                    break

    def on__item_double_clicked(self, msg: _ItemDoubleClicked) -> None:
        self.post_message(self.Activated(msg.entry))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, VideoListItem):
            self.post_message(self.Selected(event.item.entry))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, VideoListItem):
            self.post_message(self.Activated(event.item.entry))

    def on_page_indicator_prev_page(self, event: PageIndicator.PrevPage) -> None:
        event.stop()
        if self.can_go_prev():
            self.post_message(self.PageChangeRequested(-1))

    def on_page_indicator_next_page(self, event: PageIndicator.NextPage) -> None:
        event.stop()
        if self.can_go_next():
            self.post_message(self.PageChangeRequested(+1))
