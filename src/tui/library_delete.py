"""The Library tab's `D` handler: the confirmation question (what exactly goes, with sizes) and the deletion itself."""

from __future__ import annotations

from functools import partial

from src import library
from src.entries import Entry
from src.strings import text
from src.tui.fmt import escape_markup, fmt_size
from src.tui.screens.mixins.list_tools import Removal

_TITLE_MAX = 40


def ask(entries: list[Entry]) -> tuple[str, dict[str, str]]:
    """The question for ``entries`` and which key means which `safe_delete` choice."""
    if len(entries) > 1:
        total = sum(library.total_size(e) for e in entries)
        if total:
            question = text("library_delete.delete_many_sized", count=len(entries), size=fmt_size(total))
        else:
            question = text("library_delete.delete_many", count=len(entries))
        return text("list_tools.confirm", question=question), {"y": "both"}
    entry = entries[0]
    title = escape_markup((entry.get("title") or text("list_tools.untitled"))[:_TITLE_MAX])
    sizes = library.form_sizes(entry)
    if not sizes:
        return text("list_tools.confirm", question=text("library_delete.remove_missing", title=title)), {"y": "both"}
    parts = " + ".join(f"{form} {fmt_size(size) or text('library_delete.zero_size')}" for form, size in sizes.items())
    if len(sizes) == 1:
        question = text("library_delete.delete_one", title=title, parts=parts)
        return text("list_tools.confirm", question=question), {"y": "both"}
    choices = {"v": "video", "a": "audio", "b": "both"}
    return text("library_delete.choose_form", title=title, parts=parts), choices


def _delete(roots: list, entries: list[Entry], choice: str) -> list[Entry]:
    """The entries whose files went; ``choice`` is the form to delete (a single yes means both)."""
    return [e for e in entries if not library.safe_delete(e, roots, choice or "both").failed]


def removal(config, kind: str = "") -> Removal:
    """Library removal for the collection ``kind`` (`video`, `audio` or all): files are deleted outright, no undo."""
    roots = [config.video_dir, config.audio_dir]
    return Removal(
        remove=partial(_delete, roots),
        restore=lambda _entries: None,
        reload=lambda: library.of_kind(library.all_entries(config.video_dir, config.audio_dir), kind),
        noun="item",
        ask=ask,
        permanent=True,
    )
