from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Static

from src.tui.fmt import fmt_subscribers
from src.tui.widgets.thumbnail_widget import ThumbnailWidget


class ChannelInfoPanel(Vertical):
    """Channel screen, left column. ``info`` is the last dict passed to ``update_info``."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.info: dict | None = None

    def compose(self) -> ComposeResult:
        yield ThumbnailWidget(id="ch-thumbnail")
        yield Static("", id="ch-name", markup=True)
        yield Static("", id="ch-subs", markup=True)
        yield Static("", id="ch-url", markup=True)
        yield Static("", id="ch-sep", markup=False)
        with ScrollableContainer(id="ch-desc-scroll"):
            yield Static("", id="ch-desc", markup=False)

    def show_loading(self) -> None:
        self.query_one("#ch-name", Static).update("Loading...")
        self.query_one("#ch-thumbnail", ThumbnailWidget).set_loading()

    def show_error(self) -> None:
        self.query_one("#ch-name", Static).update("Could not load channel info.")

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
        self.query_one("#ch-name", Static).update(f"[bold white]{name}[/bold white]")
        self.query_one("#ch-subs", Static).update(f"[dim]{subs}[/dim]" if subs else "")
        self.query_one("#ch-url", Static).update(f"[dim]{url[:50]}[/dim]" if url else "")
        self.query_one("#ch-sep", Static).update("─" * 24)
        self.query_one("#ch-desc", Static).update((info.get("description", "") or "No description.")[:2000])
