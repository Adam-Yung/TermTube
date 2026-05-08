"""TermTube v2 — CookiesModal.

Guides the user through cookie setup: detect installed browsers, let
them pick one, trigger yt-dlp --cookies-from-browser extraction, and
show the result.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static
from textual.worker import Worker, get_current_worker

import cookies as _cookies


class CookiesModal(ModalScreen[None]):
    """Cookie manager: detect browsers, extract cookies, show status."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    CookiesModal {
        align: center middle;
    }
    #ck-box {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }
    #ck-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #ck-status-line {
        margin-bottom: 1;
        height: 1;
    }
    #ck-browser-label {
        color: $text-muted;
        margin-bottom: 0;
    }
    #ck-browser-list {
        height: 6;
        border: solid $surface-lighten-1;
        margin-bottom: 1;
    }
    #ck-message {
        color: $text;
        height: auto;
        margin-bottom: 1;
    }
    #ck-buttons {
        height: 3;
        layout: horizontal;
        align: right middle;
    }
    #ck-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, config=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._mgr = _cookies.CookieManager(config) if config else None
        self._browsers: list[str] = []
        self._selected_browser: str = ""

    def compose(self) -> ComposeResult:
        with Static(id="ck-box"):
            yield Static("🍪  Cookie Manager", id="ck-title")
            yield Static("", id="ck-status-line")
            yield Static("Select a browser to extract cookies from:", id="ck-browser-label")
            yield ListView(id="ck-browser-list")
            yield Static("", id="ck-message")
            with Static(id="ck-buttons"):
                yield Button("Close", variant="default", id="ck-close")
                yield Button("Extract cookies", variant="primary", id="ck-extract", disabled=True)

    def on_mount(self) -> None:
        self._refresh_status()
        self._load_browsers()

    def _refresh_status(self) -> None:
        if not self._mgr:
            return
        status = self._mgr.status()
        color = {"ok": "green", "stale": "yellow", "missing": "red"}.get(status, "dim")
        label = {"ok": "✓ Cookies present and fresh", "stale": "⚠ Cookies may be stale", "missing": "✗ No cookies file"}.get(status, status)
        try:
            self.query_one("#ck-status-line", Static).update(f"[{color}]{label}[/{color}]")
        except Exception:
            pass

    def _load_browsers(self) -> None:
        try:
            self._browsers = _cookies.CookieManager.detect_installed_browsers()
        except Exception:
            self._browsers = ["chrome", "firefox", "safari"]
        lv = self.query_one("#ck-browser-list", ListView)
        for b in self._browsers:
            item = ListItem(Label(b.capitalize()))
            item.data = b  # type: ignore[attr-defined]
            lv.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        browser = getattr(event.item, "data", "")
        if browser:
            self._selected_browser = browser
            try:
                btn = self.query_one("#ck-extract", Button)
                btn.disabled = False
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ck-close":
            self.dismiss()
        elif event.button.id == "ck-extract":
            self._run_extraction()

    def _run_extraction(self) -> None:
        if not self._selected_browser:
            return
        self._set_message("Extracting cookies, please wait…")
        try:
            btn = self.query_one("#ck-extract", Button)
            btn.disabled = True
        except Exception:
            pass
        self.run_worker(self._extract_worker, thread=True)

    def _extract_worker(self) -> None:
        worker = get_current_worker()
        if not self._mgr:
            self.app.call_from_thread(self._set_message, "No config available.")
            return
        try:
            ok = self._mgr.auto_refresh(self._selected_browser)
            if ok:
                self.app.call_from_thread(self._set_message, f"✓ Cookies extracted from {self._selected_browser}!")
                self.app.call_from_thread(self._refresh_status)
            else:
                self.app.call_from_thread(self._set_message, f"✗ Failed to extract cookies from {self._selected_browser}. Make sure the browser is installed and not running.")
        except Exception as exc:
            self.app.call_from_thread(self._set_message, f"Error: {exc}")
        finally:
            try:
                self.app.call_from_thread(
                    lambda: setattr(self.query_one("#ck-extract", Button), "disabled", False)
                )
            except Exception:
                pass

    def _set_message(self, text: str) -> None:
        try:
            self.query_one("#ck-message", Static).update(text)
        except Exception:
            pass
