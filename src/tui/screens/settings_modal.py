"""SettingsModal — in-TUI configuration editor."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

_THEMES = [
    ("crimson",  "🔴  Crimson   — deep red accents (default)"),
    ("amber",    "🟠  Amber     — warm orange"),
    ("ocean",    "🔵  Ocean     — cool teal / cyan"),
    ("midnight", "🟣  Midnight  — soft purple"),
]

_QUALITY_OPTS = [
    ("best",  "best  — highest available"),
    ("1080",  "1080p — Full HD"),
    ("720",   "720p  — HD"),
    ("480",   "480p  — SD"),
    ("360",   "360p  — low"),
]

_THUMB_OPTS = [
    ("auto",    "auto    — best available (default)"),
    ("symbols", "symbols — Unicode block art"),
    ("ascii",   "ascii   — ASCII only (most compatible)"),
]


class _ChoiceItem(ListItem):
    def __init__(self, value: str, label: str) -> None:
        super().__init__()
        self.value = value
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(self._label, markup=False)


class SettingsModal(ModalScreen[None]):
    """Settings screen: theme, quality, thumbnail format, browser."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=True),
        Binding("j",      "cursor_down", show=False),
        Binding("k",      "cursor_up",   show=False),
        Binding("tab",    "next_section", "Next section", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._active_list = "theme"

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("⚙  Settings", id="settings-title", markup=True)
            with ScrollableContainer(id="settings-scroll"):
                yield Static("[bold #ff6666]Theme[/bold #ff6666]", id="s-theme-head", markup=True)
                yield ListView(id="theme-list")
                yield Static("[bold #ff6666]Preferred Quality[/bold #ff6666]", id="s-quality-head", markup=True)
                yield ListView(id="quality-list-s")
                yield Static("[bold #ff6666]Thumbnail Format[/bold #ff6666]", id="s-thumb-head", markup=True)
                yield ListView(id="thumb-list")
                yield Static("[bold #ff6666]Cookie Browser[/bold #ff6666]", id="s-browser-head", markup=True)
                yield ListView(id="browser-list")
            yield Static(
                "[dim]Enter[/dim] select  ·  [dim]Tab[/dim] next section  ·  [dim]Esc[/dim] close",
                id="settings-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        config = self.app.config  # type: ignore[attr-defined]

        # Theme list
        tl = self.query_one("#theme-list", ListView)
        for val, label in _THEMES:
            item = _ChoiceItem(val, ("▶ " if val == config.theme else "  ") + label)
            tl.append(item)
        tl.focus()

        # Quality list
        ql = self.query_one("#quality-list-s", ListView)
        cur_q = config.preferred_quality
        for val, label in _QUALITY_OPTS:
            item = _ChoiceItem(val, ("▶ " if val == cur_q else "  ") + label)
            ql.append(item)

        # Thumbnail format list
        tfl = self.query_one("#thumb-list", ListView)
        cur_tf = config.thumbnail_format
        for val, label in _THUMB_OPTS:
            item = _ChoiceItem(val, ("▶ " if val == cur_tf else "  ") + label)
            tfl.append(item)

        # Browser list
        bl = self.query_one("#browser-list", ListView)
        cur_b = config.get("browser", "chrome")
        for val, label in [("chrome","Chrome"), ("firefox","Firefox"), ("brave","Brave"), ("safari","Safari")]:
            item = _ChoiceItem(val, ("▶ " if val == cur_b else "  ") + label)
            bl.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, _ChoiceItem):
            return
        config = self.app.config  # type: ignore[attr-defined]
        lv_id = event.list_view.id

        if lv_id == "theme-list":
            config._data["theme"] = event.item.value
            self.app.remove_class("theme-crimson", "theme-amber", "theme-ocean", "theme-midnight")
            self.app.add_class(f"theme-{event.item.value}")
            self._refresh_list("theme-list", _THEMES, event.item.value)

        elif lv_id == "quality-list-s":
            config._data["preferred_quality"] = event.item.value
            self._refresh_list("quality-list-s", _QUALITY_OPTS, event.item.value)

        elif lv_id == "thumb-list":
            config._data["thumbnail_format"] = event.item.value
            self._refresh_list("thumb-list", _THUMB_OPTS, event.item.value)

        elif lv_id == "browser-list":
            config._data["browser"] = event.item.value
            browsers = [("chrome","Chrome"), ("firefox","Firefox"), ("brave","Brave"), ("safari","Safari")]
            self._refresh_list("browser-list", browsers, event.item.value)

        # Persist immediately
        config.save()

    def _refresh_list(self, list_id: str, opts: list, selected: str) -> None:
        lv = self.query_one(f"#{list_id}", ListView)
        lv.clear()
        for val, label in opts:
            item = _ChoiceItem(val, ("▶ " if val == selected else "  ") + label)
            lv.append(item)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        try:
            self.focused.action_cursor_down()  # type: ignore[union-attr]
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        try:
            self.focused.action_cursor_up()  # type: ignore[union-attr]
        except Exception:
            pass

    def action_next_section(self) -> None:
        lists = ["theme-list", "quality-list-s", "thumb-list", "browser-list"]
        for i, lid in enumerate(lists):
            lv = self.query_one(f"#{lid}", ListView)
            if lv.has_focus:
                next_lv = self.query_one(f"#{lists[(i + 1) % len(lists)]}", ListView)
                next_lv.focus()
                return
        self.query_one("#theme-list", ListView).focus()
