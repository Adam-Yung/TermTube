from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from textual.events import Key

from src.entries import Entry
from src.tui.fmt import escape_markup

_UNDO_WINDOW_S = 30.0
_TITLE_MAX = 40

_NOT_REMOVABLE = {
    "home": "Home rows cannot be removed.",
    "subscriptions": "Subscriptions cannot be removed here.",
    "search": "Search results cannot be removed.",
}


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


class ListToolsMixin:
    """Mark, remove (`D`, one inline confirmation) and undo for a screen with one ``VideoListPanel``.

    The screen supplies ``_removals()``, a dict from tab id to ``Removal``; a tab without an entry says why
    through ``_hint``. Needs ``_list()``, ``_selected_entry()``, ``_detail()``, ``_current_tab`` and ``_hint``.
    """

    HAS_LIST_TOOLS = True

    def _removals(self) -> dict[str, Removal]:
        return {}

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

    def action_delete(self) -> None:
        removal = self._removals().get(self._current_tab)
        if removal is None:
            self._hint(_NOT_REMOVABLE.get(self._current_tab, "Nothing here can be removed."))
            return
        panel = self._list()
        targets = panel.marked_entries()
        if not targets:
            entry = self._selected_entry()
            targets = [entry] if entry else []
        if not targets:
            self._hint("Nothing selected.", "information")
            return
        if removal.ask is not None:
            question, choices = removal.ask(targets)
        else:
            if len(targets) == 1:
                title = escape_markup((targets[0].get("title") or "Untitled")[:_TITLE_MAX])
                question = f'Remove "{title}"?'
            else:
                question = f"Remove {len(targets)} items?"
            question = f"[bold]{question}[/bold]   [bold]y[/bold] / [dim]N[/dim]"
            choices = {"y": ""}
        self._pending_remove = (targets, choices)
        self._detail().action_bar.show_prompt(question)

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
        tab = self._current_tab
        removal = self._removals()[tab]
        panel = self._list()
        visible = panel.visible_ids()
        gone = {t.get("id") for t in targets}
        keep_at = next((i for i, vid in enumerate(visible) if vid in gone), 0)
        neighbour = next((v for v in visible[keep_at:] if v not in gone), None) or next(
            (v for v in reversed(visible[:keep_at]) if v not in gone), None
        )
        removed = removal.remove(targets, choice)
        panel.replace_entries(removal.reload(), focus_id=neighbour)
        count = len(removed)
        noun = f"{removal.noun}{'' if count == 1 else 's'}"
        if removal.permanent:
            self._undo = None
            failed = len(targets) - count
            tail = f" {failed} could not be deleted." if failed else ""
            self.notify(f"Deleted {count} {noun}. The files are gone; u cannot undo this.{tail}", timeout=6)
            return
        self._undo = (tab, removed, time.monotonic())
        self.notify(f"Removed {count} {noun}. Press u to undo.", timeout=4)

    def action_undo(self) -> None:
        if self._undo is None or time.monotonic() - self._undo[2] > _UNDO_WINDOW_S:
            self._undo = None
            self._hint("Nothing to undo.", "information")
            return
        tab, records, _ = self._undo
        self._undo = None
        removal = self._removals()[tab]
        removal.restore(records)
        if tab == self._current_tab:
            self._list().replace_entries(removal.reload(), focus_id=records[0].get("id"))
        count = len(records)
        self.notify(f"Restored {count} {removal.noun}{'' if count == 1 else 's'} to {tab.title()}.", timeout=4)
