from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from textual.events import Key

from src.entries import Entry
from src.strings import text
from src.tui.fmt import escape_markup

_UNDO_WINDOW_S = 30.0
_TITLE_MAX = 40

_NOT_REMOVABLE = {
    "home": "list_tools.not_removable_home",
    "subscriptions": "list_tools.not_removable_subscriptions",
    "search": "list_tools.not_removable_search",
    "history:wl": "list_tools.not_removable_watch_later",
    "history:yt": "list_tools.not_removable_youtube_history",
}


def _noun(removal_noun: str, count: int) -> str:
    """The removal's noun (`video`, `playlist`, `item`) in singular or plural for ``count``."""
    return text(f"list_tools.noun_{removal_noun}{'' if count == 1 else '_plural'}")


@dataclass(frozen=True)
class Removal:
    """How one tab removes rows from where they live. `reload` returns the tab's entries as they are now.

    `remove(targets, choice)` gets the choice the user's key maps to (`""` for the plain y/N question) and returns
    what it removed. `ask` replaces the plain question when a tab offers more than yes/no; `permanent` skips undo
    (the notice says files are gone).
    """

    remove: Callable[[list[Entry], str], list[Entry]]
    restore: Callable[[list[Entry]], None]
    reload: Callable[[], list[Entry]]
    noun: str
    ask: Callable[[list[Entry]], tuple[str, dict[str, str]]] | None = None  # (question markup, key -> choice)
    permanent: bool = False  # files are deleted: nothing to undo
    label: str = ""  # where a restore puts things back (default: the tab's name)


class ListToolsMixin:
    """Mark, remove (`D`, one inline confirmation) and undo for a screen with one ``VideoListPanel``.

    The screen supplies ``_removals()``, a dict from tab id to ``Removal``; a tab without an entry says why
    through ``_hint``. ``_after_removal()`` runs after a removal or an undo, for widgets that show what was removed
    (``LibraryRailMixin``). Needs ``_list()``, ``_selected_entry()``, ``_detail()``, ``_current_tab`` and ``_hint``.
    """

    def _init_list_tools(self) -> None:
        self._pending_remove: tuple[list[Entry], dict[str, str]] | None = None
        self._undo: tuple[str, list[Entry], float] | None = None

    def action_mark(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self._list().toggle_mark(entry)
        self._list().cursor_down()

    def action_mark_page(self) -> None:
        self._list().mark_page()

    def _removal_key(self) -> str:
        """Which `_removals()` entry `D` and `u` act on; the current tab unless a screen widget says otherwise."""
        return self._current_tab

    def _delete_targets(self) -> list[Entry]:
        """The marked rows, else the highlighted one; folder rows (Local tab) are never targets."""
        targets = self._list().marked_entries()
        if not targets:
            entry = self._selected_entry()
            targets = [entry] if entry else []
        return [t for t in targets if not t.get("_is_folder")]

    def action_delete(self) -> None:
        key = self._removal_key()
        removal = self._removals().get(key)
        if removal is None:
            self._hint(text(_NOT_REMOVABLE.get(key, "list_tools.not_removable_default")))
            return
        targets = self._delete_targets()
        if not targets:
            self._hint(text("list_tools.nothing_selected"), "information")
            return
        if removal.ask is not None:
            question, choices = removal.ask(targets)
        else:
            if len(targets) == 1:
                title = escape_markup((targets[0].get("title") or text("list_tools.untitled"))[:_TITLE_MAX])
                question = text("list_tools.remove_one", title=title)
            else:
                question = text("list_tools.remove_many", count=len(targets))
            question = text("list_tools.confirm", question=question)
            choices = {"y": ""}
        self._pending_remove = (targets, choices)
        self._detail().action_bar.show_prompt(question)

    def _cancel_removal_prompt(self) -> None:
        """Drop an open ``D`` question: its targets belong to a list that is gone."""
        if self._pending_remove is not None:
            self._pending_remove = None
            self._detail().action_bar.clear_prompt()

    def on_key(self, event: Key) -> None:
        """With the removal question open, a choice key confirms and any other key cancels; none reaches a binding."""
        if self._pending_remove is None:
            return
        event.stop()
        event.prevent_default()
        (targets, choices), self._pending_remove = self._pending_remove, None
        self._detail().action_bar.clear_prompt()
        if event.key in choices:
            self._remove(targets, choices[event.key])

    def _remove(self, targets: list[Entry], choice: str) -> None:
        tab = self._removal_key()
        removal = self._removals()[tab]
        panel = self._list()
        visible = panel.visible_ids()
        gone = {t.get("id") for t in targets}
        keep_at = next((i for i, vid in enumerate(visible) if vid in gone), 0)
        neighbour = next((v for v in visible[keep_at:] if v not in gone), None) or next(
            (v for v in reversed(visible[:keep_at]) if v not in gone), None
        )
        if not gone & set(visible):
            neighbour = None
        removed = removal.remove(targets, choice)
        panel.replace_entries(removal.reload(), focus_id=neighbour)
        count = len(removed)
        noun = _noun(removal.noun, count)
        if removal.permanent:
            self._undo = None
            failed = len(targets) - count
            tail = text("list_tools.delete_failed_tail", failed=failed) if failed else ""
            self.notify(text("list_tools.deleted", count=count, noun=noun, tail=tail), timeout=6)
        else:
            self._undo = (tab, removed, time.monotonic())
            self.notify(text("list_tools.removed", count=count, noun=noun), timeout=4)
        self._after_removal()
        self._refresh_actions()

    def _can_undo(self) -> bool:
        return self._undo is not None and time.monotonic() - self._undo[2] <= _UNDO_WINDOW_S

    def action_undo(self) -> None:
        if not self._can_undo():
            self._undo = None
            self._hint(text("list_tools.nothing_to_undo"), "information")
            return
        tab, records, _ = self._undo
        self._undo = None
        removal = self._removals()[tab]
        removal.restore(records)
        if tab in (self._current_tab, "playlists"):
            self._list().replace_entries(removal.reload(), focus_id=records[0].get("id"))
        self._after_removal()
        self._refresh_actions()
        count = len(records)
        noun = _noun(removal.noun, count)
        self.notify(text("list_tools.restored", count=count, noun=noun, where=removal.label or tab.title()), timeout=4)
