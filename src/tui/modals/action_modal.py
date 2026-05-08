"""TermTube v2 — ActionModal.

Context menu shown when the user presses Enter on a focused video.
Lists all available actions (play audio, play video, download, add to
playlist, hide, open in browser, copy URL).

Returns the selected action key string to the caller, or None if dismissed.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static


# Action keys returned to caller
ACTION_PLAY_AUDIO = "play_audio"
ACTION_PLAY_VIDEO = "play_video"
ACTION_DOWNLOAD_VIDEO = "download_video"
ACTION_DOWNLOAD_AUDIO = "download_audio"
ACTION_ADD_PLAYLIST = "add_playlist"
ACTION_HIDE = "hide"
ACTION_COPY_URL = "copy_url"
ACTION_OPEN_BROWSER = "open_browser"
ACTION_CHANNEL = "channel"


class ActionModal(ModalScreen[str | None]):
    """Per-video context menu."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel"),
    ]

    DEFAULT_CSS = """
    ActionModal {
        align: center middle;
    }
    #action-box {
        width: 46;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }
    #action-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
        height: auto;
        overflow: hidden;
    }
    #action-list {
        height: auto;
    }
    """

    _MENU: list[tuple[str, str]] = [
        (ACTION_PLAY_AUDIO,    "♫  Play audio"),
        (ACTION_PLAY_VIDEO,    "▶  Play video (mpv window)"),
        (ACTION_DOWNLOAD_VIDEO,"↓V  Download video"),
        (ACTION_DOWNLOAD_AUDIO,"↓A  Download audio (mp3)"),
        (ACTION_ADD_PLAYLIST,  "♬  Add to playlist…"),
        (ACTION_CHANNEL,       "⊞  Go to channel"),
        (ACTION_HIDE,          "✕  Hide this video"),
        (ACTION_COPY_URL,      "⎘  Copy URL"),
        (ACTION_OPEN_BROWSER,  "⬡  Open in browser"),
    ]

    def __init__(self, title: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._video_title = title

    def compose(self) -> ComposeResult:
        with Static(id="action-box"):
            short = (self._video_title[:40] + "…") if len(self._video_title) > 40 else self._video_title
            yield Static(short or "Video actions", id="action-title")
            lv = ListView(id="action-list")
            yield lv

    def on_mount(self) -> None:
        lv = self.query_one("#action-list", ListView)
        for key, label in self._MENU:
            item = ListItem(Label(label))
            item.data = key  # type: ignore[attr-defined]
            lv.append(item)
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = getattr(event.item, "data", None)
        if key:
            self.dismiss(key)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
