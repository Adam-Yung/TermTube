from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Static

from src import history, search_history
from src.browsers import YTDLP_SUPPORTED_BROWSERS, detect_installed_browsers, get_browser_label
from src.tui.fmt import escape_markup
from src.tui.screens.quality_modal import QualityModal
from src.tui.settings_fields import FIELDS, SECTIONS, Field, Refused
from src.tui.widgets.action_bar import ActionBar
from src.tui.widgets.video_list import VideoListItem

_EDIT_KEYS_BLOCKED = frozenset({"cursor_down", "cursor_up", "activate", "reset_default"})
_PLAIN_KINDS = frozenset({"bool", "choice", "text", "int"})
_HINT = (
    "[dim]Enter[/dim] change  ·  [dim]Space[/dim] toggle  ·  [dim]Backspace[/dim] default  ·  "
    "[dim]Tab[/dim] next section  ·  [dim]Esc[/dim] close"
)


class _Section(ListItem):
    def __init__(self, title: str) -> None:
        super().__init__(classes="settings-section", disabled=True)
        self._title = title

    def compose(self) -> ComposeResult:
        yield Static(self._title, markup=False)


class _Row(ListItem):
    """One setting. Read-only ``info`` rows are disabled so the cursor skips them."""

    def __init__(self, fld: Field, text: str) -> None:
        super().__init__(classes="settings-row", disabled=fld.kind == "info")
        self.fld = fld
        self._text = text

    def compose(self) -> ComposeResult:
        yield Static(self._text, markup=False)

    def set_text(self, text: str) -> None:
        self.query_one(Static).update(text)


class SettingsModal(ModalScreen[None]):
    """Settings in sections. Every change is saved at once; ``Backspace`` puts a row back to its default.

    ``d`` is bound globally in the lists, so reset is on Backspace (a text field keeps Backspace for itself).
    """

    BINDINGS = [
        Binding("escape",    "close", "Close", show=True),
        Binding("j",         "cursor_down", show=False),
        Binding("k",         "cursor_up", show=False),
        Binding("tab",       "next_section", show=False),
        Binding("shift+tab", "prev_section", show=False),
        Binding("space",     "activate", show=False),
        Binding("backspace", "reset_default", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._editing: _Row | None = None
        self._armed: str | None = None

    def compose(self) -> ComposeResult:
        config = self.app.config  # type: ignore[attr-defined]
        items: list[ListItem] = []
        for section in SECTIONS:
            items.append(_Section(section))
            items += [_Row(f, self._text(f)) for f in FIELDS if f.section == section]
        with Vertical(id="settings-dialog"):
            yield Static("⚙  Settings", id="settings-title", markup=True)
            yield Static(f"Config file: {config.path}", id="settings-path", markup=False)
            yield ListView(*items, id="settings-list")
            yield Input(id="settings-input")
            yield Static("", id="settings-status", markup=True)
            yield Static(_HINT, id="settings-hint", markup=True)

    def on_mount(self) -> None:
        self.query_one("#settings-input", Input).display = False
        self._list.focus()

    @property
    def _list(self) -> ListView:
        return self.query_one("#settings-list", ListView)

    def _text(self, fld: Field) -> str:
        if fld.kind == "action":
            return fld.label
        return f"{fld.label:<24}{fld.show(self.app.config)}"  # type: ignore[attr-defined]

    def _say(self, text: str, color: str = "dim") -> None:
        try:
            self.query_one("#settings-status", Static).update(f"[{color}]{escape_markup(text)}[/{color}]")
        except Exception:  # the modal closed while a worker was still running
            pass

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if self._editing is not None and action in _EDIT_KEYS_BLOCKED:
            return False
        return True

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._armed = None
        row = event.item
        if isinstance(row, _Row):
            self._say(row.fld.note)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, _Row):
            self._activate(event.item)

    def action_activate(self) -> None:
        row = self._list.highlighted_child
        if isinstance(row, _Row):
            self._activate(row)

    def _activate(self, row: _Row) -> None:
        fld = row.fld
        config = self.app.config  # type: ignore[attr-defined]
        if fld.kind == "bool":
            self._commit(fld, not fld.read(config))
        elif fld.kind == "choice":
            self._pick(fld)
        elif fld.kind in ("text", "int"):
            self._begin_edit(row)
        elif fld.kind == "action":
            self._run_action(fld)

    def _commit(self, fld: Field, value: object) -> None:
        self.app.config.set(fld.key, value)  # type: ignore[attr-defined]
        self._persist(fld, "Saved")

    def action_reset_default(self) -> None:
        row = self._list.highlighted_child
        if isinstance(row, _Row) and row.fld.kind in _PLAIN_KINDS:
            self.app.config.reset(row.fld.key)  # type: ignore[attr-defined]
            self._persist(row.fld, "Reset to the default")

    def _persist(self, fld: Field, verb: str) -> None:
        if self.app.config.save():  # type: ignore[attr-defined]
            self._say(f"{verb}. {fld.note}".strip(), "green")
        else:
            self._say("Could not write the config file; the change lasts until you quit.", "red")
        if fld.key == "theme":
            self._apply_theme()
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        for row in self._list.query(_Row):
            row.set_text(self._text(row.fld))

    def _pick(self, fld: Field) -> None:
        options = self._browser_options() if fld.key == "browser" else fld.options

        def chosen(value: str | None) -> None:
            if value is not None:
                self._commit(fld, value)

        self.app.push_screen(
            QualityModal(
                choices=[(label, value) for value, label in options],
                title=fld.label,
                current=str(fld.read(self.app.config)),  # type: ignore[attr-defined]
            ),
            chosen,
        )

    @staticmethod
    def _browser_options() -> list[tuple[str, str]]:
        detected = detect_installed_browsers()
        found = {b["name"] for b in detected}
        options = [("auto", "Auto-detect"), ("none", "None — signed out, no cookies")]
        options += [(b["name"], b["label"]) for b in detected]
        return options + [
            (name, f"{get_browser_label(name)} (not found)") for name in YTDLP_SUPPORTED_BROWSERS if name not in found
        ]

    def _begin_edit(self, row: _Row) -> None:
        self._editing = row
        field_input = self.query_one("#settings-input", Input)
        field_input.value = row.fld.show(self.app.config)  # type: ignore[attr-defined]
        field_input.display = True
        field_input.focus()
        self._say(f"{row.fld.note + '. ' if row.fld.note else ''}Enter saves, Esc cancels.")

    def _end_edit(self) -> None:
        self._editing = None
        self.query_one("#settings-input", Input).display = False
        self._list.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        row = self._editing
        if row is None or row.fld.parse is None:
            return
        try:
            value = row.fld.parse(event.value)
        except Refused as exc:
            self._say(str(exc), "red")
            return
        self._end_edit()
        self._commit(row.fld, value)

    def _run_action(self, fld: Field) -> None:
        if fld.key == "reload":
            self._reload()
        elif self._armed != fld.key:
            self._armed = fld.key
            self._say(f"{fld.label}? Press Enter again to confirm, or move away to cancel.", "yellow")
        else:
            self._armed = None
            if fld.key == "clear_cache":
                self._clear_cache()
            elif fld.key == "clear_history":
                history.clear()
                self._say("Watch history cleared.", "green")
            elif fld.key == "clear_search_history":
                search_history.clear()
                self._say("Search history cleared.", "green")

    @work(thread=True, exclusive=True, group="settings_clear")
    def _clear_cache(self) -> None:
        removed = self.app.cache.clear_all()  # type: ignore[attr-defined]
        self.app.call_from_thread(self._say, f"Cache cleared ({removed} files).", "green")

    def _reload(self) -> None:
        config = self.app.config  # type: ignore[attr-defined]
        error = config.reload()
        if error:
            self._say(f"Reload failed: {error}. Keeping the settings in memory.", "red")
            return
        self._apply_theme()
        self._refresh_rows()
        self._say(f"Reloaded {config.path.name} from disk.", "green")

    def _apply_theme(self) -> None:
        theme = self.app.config.theme  # type: ignore[attr-defined]
        self.app.remove_class("theme-crimson", "theme-amber", "theme-ocean", "theme-midnight")
        self.app.add_class(f"theme-{theme}")
        self._refresh_live_theme()

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

    def action_close(self) -> None:
        if self._editing is not None:
            self._end_edit()
            self._say("Cancelled.")
        else:
            self.dismiss(None)

    def action_cursor_down(self) -> None:
        self._list.action_cursor_down()

    def action_cursor_up(self) -> None:
        self._list.action_cursor_up()

    def action_next_section(self) -> None:
        self._jump_section(1)

    def action_prev_section(self) -> None:
        self._jump_section(-1)

    def _jump_section(self, step: int) -> None:
        if self._editing is not None:
            return
        lv = self._list
        starts = [i + 1 for i, child in enumerate(lv.children) if isinstance(child, _Section)]
        here = max((n for n, s in enumerate(starts) if s <= (lv.index or 0)), default=0)
        lv.index = starts[(here + step) % len(starts)]
