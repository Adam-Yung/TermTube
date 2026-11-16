from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from src.browsers import YTDLP_SUPPORTED_BROWSERS, detect_installed_browsers, get_browser_label
from src.tui.widgets.action_bar import ActionBar
from src.tui.widgets.video_list import VideoListItem

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
        self._browser_opts: list[tuple[str, str]] = []

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
                yield Static("[bold #ff6666]Browser[/bold #ff6666]", id="s-browser-head", markup=True)
                yield Static("", id="s-browser-status", markup=True)
                yield ListView(id="browser-list")
            yield Static(
                "[dim]Enter[/dim] select  ·  [dim]Tab[/dim] next section  ·  [dim]Esc[/dim] close",
                id="settings-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        config = self.app.config  # type: ignore[attr-defined]
        self._refresh_list("theme-list", _THEMES, config.theme)
        self._refresh_list("quality-list-s", _QUALITY_OPTS, config.preferred_quality)
        self._refresh_list("thumb-list", _THUMB_OPTS, config.thumbnail_format)
        self.query_one("#theme-list", ListView).focus()

        cur_browser = config.get("browser", "auto")
        if cur_browser and cur_browser.lower() != "none":
            status_line = f"  [dim]mode:[/dim] [green]browser session[/green] ({cur_browser})"
        else:
            status_line = "  [dim]mode:[/dim] [yellow]none (unauthenticated)[/yellow]"
        self.query_one("#s-browser-status", Static).update(status_line)

        detected = detect_installed_browsers()
        detected_names = {b["name"] for b in detected}
        self._browser_opts = [("auto", "Auto-detect")]
        self._browser_opts += [(b["name"], b["label"]) for b in detected]
        self._browser_opts += [
            (name, f"{get_browser_label(name)} (not found)")
            for name in YTDLP_SUPPORTED_BROWSERS
            if name not in detected_names
        ]
        self._refresh_list("browser-list", self._browser_opts, cur_browser)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, _ChoiceItem):
            return
        config = self.app.config  # type: ignore[attr-defined]
        lv_id = event.list_view.id

        if lv_id == "theme-list":
            config.set("theme", event.item.value)
            self.app.remove_class("theme-crimson", "theme-amber", "theme-ocean", "theme-midnight")
            self.app.add_class(f"theme-{event.item.value}")
            self._refresh_list("theme-list", _THEMES, event.item.value)
            self._refresh_live_theme()

        elif lv_id == "quality-list-s":
            config.set("preferred_quality", event.item.value)
            self._refresh_list("quality-list-s", _QUALITY_OPTS, event.item.value)

        elif lv_id == "thumb-list":
            config.set("thumbnail_format", event.item.value)
            self._refresh_list("thumb-list", _THUMB_OPTS, event.item.value)

        elif lv_id == "browser-list":
            config.set("browser", event.item.value)
            self._refresh_list("browser-list", self._browser_opts, event.item.value)

        config.save()

    def _refresh_live_theme(self) -> None:
        """Re-render Rich-markup widgets that bake the theme color at compose time."""
        for item in self.app.query(VideoListItem):
            try:
                item._cached_markup = item._build_markup()
                item.query_one(Static).update(item._cached_markup)
            except Exception:
                pass
        for ab in self.app.query(ActionBar):
            try:
                ab.refresh_theme()
            except Exception:
                pass

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
