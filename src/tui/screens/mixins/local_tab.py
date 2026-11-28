from __future__ import annotations

from pathlib import Path

from src import local_files, logger
from src.entries import Entry
from src.strings import text
from src.tui.fmt import escape_markup, fmt_size
from src.tui.screens.mixins.list_tools import Removal
from src.tui.widgets.video_list import VideoListPanel

LOCAL_TAB = "local"
_TITLE_MAX = 40


def _ask(entries: list[Entry]) -> tuple[str, dict[str, str]]:
    """The `D` question: the files go for good after one yes (folder rows never reach it)."""
    files = entries
    size = fmt_size(sum(e.get("_size") or 0 for e in files)) or text("library_delete.zero_size")
    if len(files) == 1:
        title = escape_markup(files[0]["title"][:_TITLE_MAX])
        question = text("local_tab.delete_one", title=title, size=size)
    else:
        question = text("local_tab.delete_many", count=len(files), size=size)
    return text("list_tools.confirm", question=question), {"y": ""}


class LocalTabMixin:
    """The Local tab: one folder on disk as rows. Folder rows open in place; Backspace and the `..` row go up.

    The listing runs on the loader thread (``_source_loader`` maps the tab here); file details are probed by
    ``DetailFocusMixin``. Needs ``_ui``, ``_load_view``, ``_feed_session``, ``_rail_focused`` and ``_hint``.
    """

    def _init_local_tab(self) -> None:
        self._local_dir = local_files.launch_dir()
        self._local_rows: list[Entry] = []
        self._local_focus: str | None = None

    def _load_local(self, panel: VideoListPanel) -> None:
        session = self._feed_session
        listing = local_files.list_folder(self._local_dir, cancelled=lambda: session != self._feed_session)
        self._ui(self._show_local, panel, listing)

    def _show_local(self, panel: VideoListPanel, listing: local_files.Listing) -> None:
        self._local_rows = listing.entries
        panel.set_breadcrumb(escape_markup(str(self._local_dir)))
        if listing.error:
            self._hint(listing.error)
        if not listing.entries:
            panel.set_empty_message(text("local_tab.empty"))
            return
        panel.add_entries(1, listing.entries, evict=False)
        index = next((i for i, e in enumerate(listing.entries) if e["id"] == self._local_focus), 0)
        panel.load_page(index // panel.page_size + 1, focus_id=self._local_focus, focus=not self._rail_focused())
        panel.finish_loading()

    def _open_folder(self, entry: Entry) -> None:
        """Show the folder of a folder row; going up lands on the folder just left."""
        target = Path(entry["_local_path"])
        self._local_focus = local_files.folder_row(str(self._local_dir), "")["id"] if entry.get("_is_parent") else None
        self._local_dir = target
        logger.info("local folder changed")
        self._load_view(LOCAL_TAB)

    def _local_up(self) -> None:
        """From ``_local_dir``, not the rows: those still show the previous folder while the next one loads."""
        current = Path(self._local_dir)
        if current.parent == current:
            self._hint(text("local_tab.at_root"), "information")
        else:
            self._open_folder({"title": "..", "_local_path": str(current.parent), "_is_parent": True})

    def _local_removal(self) -> Removal:
        return Removal(remove=self._delete_local, restore=lambda _entries: None, reload=lambda: list(self._local_rows),
                       noun="file", ask=_ask, permanent=True)

    def _delete_local(self, entries: list[Entry], _choice: str) -> list[Entry]:
        gone: list[Entry] = []
        for entry in entries:
            reason = local_files.delete_file(entry)
            if reason:
                self._hint(text("local_tab.delete_refused", title=entry["title"][:_TITLE_MAX], reason=reason))
            else:
                gone.append(entry)
        ids = {e["id"] for e in gone}
        self._local_rows = [e for e in self._local_rows if e["id"] not in ids]
        return gone
