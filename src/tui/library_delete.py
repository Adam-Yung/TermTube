"""The Library tab's `D` handler: the confirmation question (what exactly goes, with sizes) and the deletion itself."""

from __future__ import annotations

from src import library
from src.entries import Entry
from src.tui.fmt import escape_markup, fmt_size
from src.tui.screens.mixins.list_tools import Removal

_TITLE_MAX = 40


def ask(entries: list[Entry]) -> tuple[str, dict[str, str]]:
    """The question for ``entries`` and which key means which `safe_delete` choice."""
    if len(entries) > 1:
        total = sum(library.total_size(e) for e in entries)
        size = f" ({fmt_size(total)})" if total else ""
        return f"[bold]Delete {len(entries)} items{size}?[/bold]   [bold]y[/bold] / [dim]N[/dim]", {"y": "both"}
    entry = entries[0]
    title = escape_markup((entry.get("title") or "Untitled")[:_TITLE_MAX])
    sizes = library.form_sizes(entry)
    if not sizes:
        return f'[bold]Remove "{title}" (file missing)?[/bold]   [bold]y[/bold] / [dim]N[/dim]', {"y": "entry_only"}
    parts = " + ".join(f"{form} {fmt_size(size) or '0 B'}" for form, size in sizes.items())
    if len(sizes) == 1:
        return f'[bold]Delete "{title}" - {parts}?[/bold]   [bold]y[/bold] / [dim]N[/dim]', {"y": "both"}
    keys = (
        "[bold]v[/bold] video / [bold]a[/bold] audio / [bold]b[/bold] both / [bold]e[/bold] entry only"
        " / [dim]N[/dim] cancel"
    )
    choices = {"v": "video", "a": "audio", "b": "both", "e": "entry_only"}
    return f'[bold]Delete "{title}" - {parts}?[/bold]   {keys}', choices


def removal(config) -> Removal:
    """Library removal: files are deleted outright, so there is nothing to undo."""
    roots = [config.video_dir, config.audio_dir]

    def remove(entries: list[Entry], choice: str) -> list[Entry]:
        return [e for e in entries if not library.safe_delete(e, roots, choice or "both").failed]

    return Removal(
        remove=remove,
        restore=lambda _entries: None,
        reload=lambda: library.all_entries(config.video_dir, config.audio_dir),
        noun="item",
        ask=ask,
        permanent=True,
    )
