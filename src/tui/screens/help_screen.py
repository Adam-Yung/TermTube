"""HelpScreen — full-page reference for all keyboard shortcuts and features."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src.strings import text

_RULE = "[bold #888888]" + "─" * 70 + "[/bold #888888]"

# (section id, [(key combination, row id)]): the section title and each row's description live in strings.json
# under help_screen.<section>_title and help_screen.<section>_<row>.
_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("move", [
        ("j / k", "cursor"),
        ("h / l  ← / →", "page"),
        ("g / G", "ends"),
        ("H / L", "tab"),
        ("Enter", "menu"),
        ("Backspace / Esc", "back"),
        ("F1–F6  `", "jump"),
    ]),
    ("play", [
        ("v / V", "watch"),
        ("a / A", "audio"),
        ("e", "enqueue"),
        (">", "skip"),
        ("<", "previous"),
        ("Q", "queue"),
        ("Space", "pause"),
        ("x", "stop"),
        ("[ / ]", "seek5"),
        ("{ / }", "seek10"),
        ("0–9", "seek_pct"),
    ]),
    ("player", [
        ("h / l  ← / →", "seek5"),
        ("H / L", "seek10"),
        ("Space  0–9", "pause"),
        ("q / Esc", "stop"),
    ]),
    ("row", [
        ("d", "download"),
        ("c", "channel"),
        ("p", "playlist"),
        ("y", "copy"),
        ("b", "browser"),
    ]),
    ("tools", [
        ("f", "filter"),
        ("m / M", "mark"),
        ("D", "remove"),
        ("u", "undo"),
    ]),
    ("rail", [
        ("Tab", "rail"),
        ("j / k  Enter", "rail_nav"),
    ]),
    ("library", [
        ("f", "filter"),
        ("n / R", "playlist_new"),
        ("D", "delete"),
        ("J / K", "reorder"),
        ("P / S / E", "playlist_play"),
        ("p", "playlist_dialog"),
    ]),
    ("history", [
        ("I", "import"),
    ]),
    ("app", [
        ("/", "search"),
        ("s / t", "sort"),
        ("r", "refresh"),
        ("Z", "hide_played"),
        (",", "settings"),
        ("?", "help"),
        ("Ctrl+D", "debug"),
        ("q", "quit"),
    ]),
    ("channel", [
        ("s", "sort"),
        ("r", "reload"),
        ("i", "description"),
        ("Enter", "playlist"),
        ("B", "follow"),
        ("o", "owner"),
        ("P E S", "playlist_bulk"),
        ("/ , ? q", "global"),
        ("Esc", "back"),
    ]),
]

_CONFIG_KEYS = [
    ("browser", "config_browser"),
    ("preferred_quality", "config_quality"),
    ("video_dir", "config_video_dir"),
    ("audio_dir", "config_audio_dir"),
]


def _render_help(color: str) -> str:
    title = text("help_screen.title")
    lines = [f"[bold {color}]{title}[/bold {color}]", ""]
    for section, rows in _SECTIONS:
        lines += [_RULE, f"[bold white]{text(f'help_screen.{section}_title')}[/bold white]", _RULE, ""]
        lines += [f"  [{color}]{key:<16}[/{color}] {text(f'help_screen.{section}_{row}')}" for key, row in rows]
        lines.append("")
    lines += [_RULE, f"[bold white]{text('help_screen.config_title')}[/bold white]", _RULE, ""]
    lines += [f"  [{color}]{key:<18}[/{color}] {text(f'help_screen.{row}')}" for key, row in _CONFIG_KEYS]
    lines += ["", "  " + text("help_screen.close_hint")]
    return "\n".join(lines)


class HelpScreen(ModalScreen[None]):
    """Full-page keyboard reference, openable via ? or the Help tab."""

    BINDINGS = [
        Binding("?", "close", "Close", show=True),
        Binding("q", "close", "Close", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    def _get_theme_color(self) -> str:
        try:
            theme = self.app.config.theme
        except Exception:
            theme = "crimson"
        return {
            "crimson": "#ff4444",
            "amber": "#e8820c",
            "ocean": "#0ea5e9",
            "midnight": "#a855f7",
        }.get(theme, "#ff4444")

    def compose(self) -> ComposeResult:
        color = self._get_theme_color()
        content = _render_help(color)

        with Vertical(id="help-outer"):
            with ScrollableContainer(id="help-scroll"):
                yield Static(content, id="help-content", markup=True)

    def on_mount(self) -> None:
        self.query_one("#help-outer").border_title = text("help_screen.border_title")

    def action_close(self) -> None:
        self.dismiss(None)
