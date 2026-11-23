from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Static

from src.strings import text
from src.tui.fmt import escape_markup, fmt_subscribers
from src.tui.widgets.thumbnail_widget import ThumbnailWidget

_COLLAPSED_LINES = 3
_LINE_CAP = 120
_DESCRIPTION_CAP = 2000


def _description(info: dict) -> str:
    return (info.get("description", "") or text("channel_info_panel.no_description"))[:_DESCRIPTION_CAP]


def _collapse(body: str) -> tuple[str, bool]:
    """The first lines of ``body`` (each cut at ``_LINE_CAP``) and whether anything was left out."""
    lines = body.strip().splitlines()
    shown = [line[:_LINE_CAP] + ("…" if len(line) > _LINE_CAP else "") for line in lines[:_COLLAPSED_LINES]]
    more = len(lines) > _COLLAPSED_LINES or any(len(line) > _LINE_CAP for line in lines[:_COLLAPSED_LINES])
    return "\n".join(shown), more


def _stats(info: dict) -> str:
    """``442 videos · Joined Mar 3, 2011``: whichever of the two the response had."""
    count = info.get("video_count")
    key = "channel_info_panel.video_one" if count == 1 else "channel_info_panel.video_many"
    parts = [text(key, count=count)] if count else []
    if info.get("joined"):
        parts.append(info["joined"])
    return " · ".join(parts)


class ChannelInfoPanel(Vertical):
    """Channel screen, left column. ``info`` is the last dict passed to ``update_info``."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.info: dict | None = None
        self._expanded = True

    def compose(self) -> ComposeResult:
        yield ThumbnailWidget(id="ch-thumbnail")
        yield Static("", id="ch-name", markup=True)
        yield Static("", id="ch-subs", markup=True)
        yield Static("", id="ch-stats", markup=True)
        yield Static("", id="ch-url", markup=True)
        yield Static("", id="ch-sep", markup=False)
        with ScrollableContainer(id="ch-desc-scroll"):
            yield Static("", id="ch-desc", markup=False)
        yield Static("", id="ch-desc-hint", markup=True)

    def show_loading(self) -> None:
        self.query_one("#ch-name", Static).update(text("channel_info_panel.loading"))
        self.query_one("#ch-thumbnail", ThumbnailWidget).set_loading()

    def show_error(self) -> None:
        self.query_one("#ch-name", Static).update(text("channel_info_panel.load_error"))

    def set_avatar_id(self, avatar_id: str) -> None:
        self.query_one("#ch-thumbnail", ThumbnailWidget).set_video_id(avatar_id)

    def set_thumbnail_image(self, avatar_id: str, path: Path) -> None:
        self.query_one("#ch-thumbnail", ThumbnailWidget).set_image_path(avatar_id, path)

    def set_thumbnail_ansi(self, avatar_id: str, ansi: str) -> None:
        self.query_one("#ch-thumbnail", ThumbnailWidget).set_ansi(avatar_id, ansi)

    def set_thumbnail_loading(self) -> None:
        self.query_one("#ch-thumbnail", ThumbnailWidget).set_loading()

    def set_thumbnail_placeholder(self) -> None:
        self.query_one("#ch-thumbnail", ThumbnailWidget).set_placeholder()

    def update_info(self, info: dict) -> None:
        self.info = info
        name = info.get("channel", "") or info.get("uploader", "")
        subs = fmt_subscribers(info.get("subscriber_count"))
        url = info.get("channel_url", "") or info.get("uploader_url", "")
        self.query_one("#ch-name", Static).update(f"[bold white]{escape_markup(name)}[/bold white]")
        self.query_one("#ch-subs", Static).update(f"[dim]{subs}[/dim]" if subs else "")
        stats = _stats(info)
        self.query_one("#ch-stats", Static).update(f"[dim]{escape_markup(stats)}[/dim]" if stats else "")
        self.query_one("#ch-url", Static).update(f"[dim]{url[:50]}[/dim]" if url else "")
        self.query_one("#ch-sep", Static).update("─" * 24)
        self._expanded = True
        self._render_description()

    def toggle_description(self) -> bool:
        """Expand or collapse the description. False when there is nothing more to show."""
        if self.info is None or not _collapse(_description(self.info))[1]:
            return False
        self._expanded = not self._expanded
        self._render_description()
        return True

    def _render_description(self) -> None:
        body = _description(self.info or {})
        shown, more = _collapse(body)
        self.query_one("#ch-desc", Static).update(body if self._expanded else shown)
        hint = text("channel_info_panel.show_less" if self._expanded else "channel_info_panel.show_all") if more else ""
        self.query_one("#ch-desc-hint", Static).update(f"[dim]{hint}[/dim]" if hint else "")
