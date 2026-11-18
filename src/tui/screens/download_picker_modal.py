from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from src.downloads import QUALITY_CHOICES
from src.strings import text

_VIDEO_DL_QUALITY = QUALITY_CHOICES
_AUDIO_DL_QUALITY = [
    ("download_picker_modal.audio_best", "bestaudio/best"),
    ("download_picker_modal.audio_medium", "bestaudio[abr<=128]/bestaudio/best"),
]

_TYPE_CHOICES = [("video", "download_picker_modal.type_video"), ("audio", "download_picker_modal.type_audio")]


class _SelectItem(ListItem):
    def __init__(self, key: str, label: str) -> None:
        super().__init__()
        self.item_key = key
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(self._label, markup=True)


class DownloadPickerModal(ModalScreen):
    """Choose video or audio, then quality. Dismisses with (type, format) or None; Esc on step 2 goes back."""

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
        with Vertical(id="dlpick-dialog", classes="dialog"):
            if self._title:
                t = self._title[:55]
                yield Static(f"[bold]{t}[/bold]", id="dlpick-video-title", markup=True)
            yield Static(text("download_picker_modal.header"), id="dlpick-header", markup=False)
            yield Static(text("download_picker_modal.sub_type"), id="dlpick-sub", markup=False)
            yield ListView(id="dlpick-list", classes="dialog-list")
            yield Static(text("download_picker_modal.hint"), id="dlpick-hint", markup=False)

    def on_mount(self) -> None:
        self._render_step1()

    def _theme_color(self) -> str:
        try:
            classes = self.app.classes
            if "theme-amber" in classes:
                return "#e8820c"
            if "theme-ocean" in classes:
                return "#0ea5e9"
            if "theme-midnight" in classes:
                return "#a855f7"
        except Exception:
            pass
        return "#ff6666"

    def _render_step1(self) -> None:
        lv = self.query_one("#dlpick-list", ListView)
        lv.clear()
        self.query_one("#dlpick-sub", Static).update(text("download_picker_modal.sub_type"))
        c = self._theme_color()
        for key, label_key in _TYPE_CHOICES:
            label = text(label_key)
            lv.append(_SelectItem(key, f"[bold {c}]{label}[/bold {c}]"))
        lv.focus()

    def _render_step2(self) -> None:
        lv = self.query_one("#dlpick-list", ListView)
        lv.clear()
        choices = _AUDIO_DL_QUALITY if self._dl_type == "audio" else _VIDEO_DL_QUALITY
        sub_key = "sub_audio_quality" if self._dl_type == "audio" else "sub_video_quality"
        self.query_one("#dlpick-sub", Static).update(text(f"download_picker_modal.{sub_key}"))
        for label, fmt in choices:
            lv.append(_SelectItem(fmt, text(label) if label.startswith("download_picker_modal.") else label))
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

