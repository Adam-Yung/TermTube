"""TermTube v2 — SettingsModal.

Edits user preferences live.  Changes are applied immediately via
Config.set() and saved to disk on close.  Theme changes are applied to
the running app.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from config import Config

_THEMES = ["crimson", "amber", "ocean", "midnight", "forest"]
_BROWSERS = ["chrome", "chromium", "firefox", "safari", "edge", "brave", "opera", "vivaldi"]


class SettingsModal(ModalScreen[None]):
    """Settings panel — applies changes on close."""

    BINDINGS = [
        Binding("escape", "close_settings", "Close"),
    ]

    DEFAULT_CSS = """
    SettingsModal {
        align: center middle;
    }
    #settings-box {
        width: 70;
        max-width: 90%;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        overflow-y: auto;
    }
    #settings-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    .settings-section {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    .settings-row {
        height: 3;
        layout: horizontal;
        align: left middle;
        margin-bottom: 0;
    }
    .settings-label {
        width: 28;
        color: $text;
    }
    .settings-input {
        width: 1fr;
    }
    #settings-close {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, config: Config, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        cfg = self._config
        with Static(id="settings-box"):
            yield Static("⚙  Settings", id="settings-title")

            # --- UI ---
            yield Static("Interface", classes="settings-section")
            with Static(classes="settings-row"):
                yield Label("Theme:", classes="settings-label")
                yield Select(
                    [(t, t) for t in _THEMES],
                    value=cfg.get("theme", "crimson"),
                    id="set-theme",
                    classes="settings-input",
                )

            # --- Playback ---
            yield Static("Playback", classes="settings-section")
            with Static(classes="settings-row"):
                yield Label("Default quality:", classes="settings-label")
                yield Input(
                    value=cfg.get("preferred_quality", "bestvideo+bestaudio/best"),
                    id="set-quality",
                    classes="settings-input",
                )
            with Static(classes="settings-row"):
                yield Label("Volume step:", classes="settings-label")
                yield Input(
                    value=str(cfg.get("volume_step", 5)),
                    id="set-vol-step",
                    classes="settings-input",
                )

            # --- SponsorBlock ---
            yield Static("SponsorBlock", classes="settings-section")
            with Static(classes="settings-row"):
                yield Label("Enable SponsorBlock:", classes="settings-label")
                yield Checkbox(
                    "",
                    value=bool(cfg.get("sponsorblock_enabled", False)),
                    id="set-sb-enabled",
                )
            with Static(classes="settings-row"):
                yield Label("Categories (csv):", classes="settings-label")
                yield Input(
                    value=",".join(cfg.get("sponsorblock_categories", ["sponsor", "selfpromo"])),
                    id="set-sb-cats",
                    classes="settings-input",
                )

            # --- Downloads ---
            yield Static("Downloads", classes="settings-section")
            with Static(classes="settings-row"):
                yield Label("Video directory:", classes="settings-label")
                yield Input(
                    value=str(cfg.video_dir),
                    id="set-video-dir",
                    classes="settings-input",
                )
            with Static(classes="settings-row"):
                yield Label("Audio directory:", classes="settings-label")
                yield Input(
                    value=str(cfg.audio_dir),
                    id="set-audio-dir",
                    classes="settings-input",
                )

            # --- Cookies ---
            yield Static("Cookies", classes="settings-section")
            with Static(classes="settings-row"):
                yield Label("Default browser:", classes="settings-label")
                yield Select(
                    [(b, b) for b in _BROWSERS],
                    value=cfg.get("browser", "chrome"),
                    id="set-browser",
                    classes="settings-input",
                )

            yield Button("Save & Close", variant="primary", id="settings-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-close":
            self.action_close_settings()

    def action_close_settings(self) -> None:
        self._apply()
        self.dismiss()

    def _apply(self) -> None:
        cfg = self._config

        def _get_input(id_: str, fallback: str = "") -> str:
            try:
                return self.query_one(f"#{id_}", Input).value.strip()
            except Exception:
                return fallback

        def _get_select(id_: str, fallback: str = "") -> str:
            try:
                val = self.query_one(f"#{id_}", Select).value
                return str(val) if val else fallback
            except Exception:
                return fallback

        def _get_checkbox(id_: str) -> bool:
            try:
                return self.query_one(f"#{id_}", Checkbox).value
            except Exception:
                return False

        theme = _get_select("set-theme", cfg.get("theme", "crimson"))
        if theme != cfg.get("theme"):
            cfg.set("theme", theme)
            try:
                self.app.apply_theme(theme)
            except Exception:
                pass

        quality = _get_input("set-quality", cfg.get("preferred_quality", "bestvideo+bestaudio/best"))
        if quality:
            cfg.set("preferred_quality", quality)

        vol_step = _get_input("set-vol-step", str(cfg.get("volume_step", 5)))
        try:
            cfg.set("volume_step", int(vol_step))
        except ValueError:
            pass

        cfg.set("sponsorblock_enabled", _get_checkbox("set-sb-enabled"))
        sb_cats_raw = _get_input("set-sb-cats", "sponsor,selfpromo")
        sb_cats = [c.strip() for c in sb_cats_raw.split(",") if c.strip()]
        if sb_cats:
            cfg.set("sponsorblock_categories", sb_cats)

        video_dir = _get_input("set-video-dir")
        if video_dir:
            cfg.set("video_dir", video_dir)

        audio_dir = _get_input("set-audio-dir")
        if audio_dir:
            cfg.set("audio_dir", audio_dir)

        browser = _get_select("set-browser", cfg.get("browser", "chrome"))
        cfg.set("browser", browser)

        cfg.save()
