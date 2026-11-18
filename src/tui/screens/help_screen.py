"""HelpScreen — full-page reference for all keyboard shortcuts and features."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

_RULE = "[bold #888888]" + "─" * 70 + "[/bold #888888]"

_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("MOVE", [
        ("j / k", "Cursor down / up"),
        ("h / l  ← / →", "Previous / next page of the list"),
        ("g / G", "First / last item of the whole list"),
        ("H / L", "Previous / next tab"),
        ("Enter", "Action menu for the row"),
        ("Backspace / Esc", "Back (out of a playlist or channel)"),
        ("F1–F7  `", "Jump to a tab / open the tab picker"),
    ]),
    ("PLAY", [
        ("v / V", "Watch video / choose quality first"),
        ("a / A", "Play audio / choose quality first (replaces the current track)"),
        ("e", "Add audio to the queue"),
        (">", "Skip to the next queued track"),
        ("Space", "Pause / resume audio"),
        ("x", "Stop audio and clear the queue"),
        ("[ / ]", "Audio seek −5 s / +5 s"),
        ("{ / }", "Audio seek −10 s / +10 s"),
        ("0–9", "Audio seek to 0%–90%"),
    ]),
    ("VIDEO PLAYER", [
        ("h / l  ← / →", "Seek −5 s / +5 s"),
        ("H / L", "Seek −10 s / +10 s"),
        ("Space  0–9", "Pause / seek to a percentage"),
        ("q / Esc", "Stop"),
    ]),
    ("ROW ACTIONS", [
        ("d", "Download (video or audio, quality picker)"),
        ("c", "Open the channel page"),
        ("p", "Add to a playlist"),
        ("y", "Copy the video URL"),
        ("b", "Open in the browser"),
    ]),
    ("LIST TOOLS", [
        ("f", "Filter the loaded list as you type (Enter keeps it, Esc clears it)"),
        ("m / M", "Mark the row and move down / mark the whole page"),
        ("D", "Remove the row or the marked rows from this list, after one y / N (History)"),
        ("u", "Undo the last removal (within 30 s)"),
    ]),
    ("APP", [
        ("/", "Search"),
        ("r", "Refresh the current feed (clears its cache)"),
        (",", "Settings"),
        ("?", "This screen"),
        ("Ctrl+D", "Debug log panel"),
        ("q", "Quit (the audio queue is not saved)"),
    ]),
    ("CHANNEL PAGE", [
        ("s", "Sort (date / views)"),
        ("r", "Reload"),
        ("/ , ? q", "Search, settings, help, quit (as on the main page)"),
        ("Esc", "Back to the previous page"),
    ]),
]

_CONFIG_KEYS = [
    ("browser", "auto / none / firefox / chrome / … (cookie source for your account feeds)"),
    ("preferred_quality", "best / 1080 / 720 / 480 / 360"),
    ("video_dir", "Download directory for videos"),
    ("audio_dir", "Download directory for audio"),
]


def _render_help(color: str) -> str:
    lines = [f"[bold {color}]TermTube — Keyboard Reference[/bold {color}]", ""]
    for title, rows in _SECTIONS:
        lines += [_RULE, f"[bold white]{title}[/bold white]", _RULE, ""]
        lines += [f"  [{color}]{key:<16}[/{color}] {text}" for key, text in rows]
        lines.append("")
    lines += [_RULE, "[bold white]CONFIG  (~/.config/TermTube/config.yaml)[/bold white]", _RULE, ""]
    lines += [f"  [{color}]{key:<18}[/{color}] {text}" for key, text in _CONFIG_KEYS]
    lines += ["", "  [dim]Press [bold]?[/bold], [bold]q[/bold] or [bold]Esc[/bold] to close.[/dim]"]
    return "\n".join(lines)


class HelpScreen(ModalScreen[None]):
    """Full-page keyboard reference, openable via ? or the Help tab."""

    BINDINGS = [
        Binding("?", "close", "Close", show=True),
        Binding("q", "close", "Close", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-outer {
        width: 80%;
        height: 90%;
        max-width: 100;
        background: #0f0f18;
        border: solid #ff4444;
        border-title-color: #ff4444;
        border-title-style: bold;
    }

    #help-scroll {
        width: 100%;
        height: 1fr;
        padding: 1 3;
    }

    #help-content {
        width: 100%;
    }
    """

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
        self.query_one("#help-outer").border_title = "❓ Help & Keyboard Reference"

    def action_close(self) -> None:
        self.dismiss(None)
