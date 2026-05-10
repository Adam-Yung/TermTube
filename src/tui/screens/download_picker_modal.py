from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from src.ytdlp import QUALITY_CHOICES

_VIDEO_DL_QUALITY = QUALITY_CHOICES
_AUDIO_DL_QUALITY = [
    ("best audio", "bestaudio/best"),
    ("medium audio (128k)", "bestaudio[abr<=128]/bestaudio/best"),
]

_TYPE_CHOICES = [("video", "DL Video"), ("audio", "DL Audio (MP3)")]


class _SelectItem(ListItem):
    def __init__(self, key: str, label: str) -> None:
        super().__init__()
        self.item_key = key
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(self._label, markup=True)


class DownloadPickerModal(ModalScreen):
    """Two-step modal: choose Video or Audio, then quality.

    Dismisses with (type, fmt_string) or None on cancel.
    Esc on step 2 goes back to step 1.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def __init__(self, title: str = "") -> None:
        super().__init__()
        self._title = title
        self._step: int = 1
        self._dl_type: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="dlpick-dialog"):
            if self._title:
                t = self._title[:55]
                yield Static(f"[bold]{t}[/bold]", id="dlpick-video-title", markup=True)
            yield Static("Download", id="dlpick-header", markup=False)
            yield Static("Choose format", id="dlpick-sub", markup=False)
            yield ListView(id="dlpick-list")
            yield Static("jk navigate  Enter select  Esc back", id="dlpick-hint", markup=False)

    def on_mount(self) -> None:
        self._render_step1()

    def _theme_color(self) -> str:
        try:
            classes = self.app.classes
            if "theme-amber" in classes: return "#e8820c"
            if "theme-ocean" in classes: return "#0ea5e9"
            if "theme-midnight" in classes: return "#a855f7"
        except Exception:
            pass
        return "#ff6666"

    def _render_step1(self) -> None:
        lv = self.query_one("#dlpick-list", ListView)
        lv.clear()
        self.query_one("#dlpick-sub", Static).update("Choose format")
        c = self._theme_color()
        ob = chr(91) + "bold " + c + chr(93)
        cb = chr(91) + "/bold " + c + chr(93)
        for key, label in _TYPE_CHOICES:
            lv.append(_SelectItem(key, ob + label + cb))
        lv.focus()

    def _render_step2(self) -> None:
        lv = self.query_one("#dlpick-list", ListView)
        lv.clear()
        choices = _AUDIO_DL_QUALITY if self._dl_type == "audio" else _VIDEO_DL_QUALITY
        mode = "audio" if self._dl_type == "audio" else "video"
        self.query_one("#dlpick-sub", Static).update("Select " + mode + " quality")
        for label, fmt in choices:
            lv.append(_SelectItem(fmt, label))
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, _SelectItem):
            return
        if self._step == 1:
            self._dl_type = event.item.item_key
            self._step = 2
            self._render_step2()
        else:
            self.dismiss((self._dl_type, event.item.item_key))

    def action_cancel(self) -> None:
        if self._step == 2:
            self._step = 1
            self._render_step1()
        else:
            self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one("#dlpick-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#dlpick-list", ListView).action_cursor_up()

