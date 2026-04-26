"""HelpScreen — full-page reference for all keyboard shortcuts and features."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

_HELP_CONTENT = """\
[bold {COLOR}]TermTube — Keyboard Reference[/bold {COLOR}]

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]NAVIGATION[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [{COLOR}]j / ↓[/{COLOR}]          Move cursor down
  [{COLOR}]k / ↑[/{COLOR}]          Move cursor up
  [{COLOR}]g[/{COLOR}]              Jump to top of list
  [{COLOR}]G[/{COLOR}]              Jump to bottom of list
  [{COLOR}]Backspace[/{COLOR}]      Go back (e.g. from playlist drill-down)
  [{COLOR}]Enter[/{COLOR}]          Open video action menu (Watch / Listen / Download / …)

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]PAGES  (F-keys or backtick picker)[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [{COLOR}]F1[/{COLOR}]             🏠  Home / Recommended
  [{COLOR}]F2[/{COLOR}]             📺  Subscriptions
  [{COLOR}]F3[/{COLOR}]             🔍  Search
  [{COLOR}]F4[/{COLOR}]             🕐  History
  [{COLOR}]F5[/{COLOR}]             📁  Library (downloaded files)
  [{COLOR}]F6[/{COLOR}]             🎵  Playlists
  [{COLOR}]F7[/{COLOR}]             ❓  Help (this screen)
  [{COLOR}]`  (backtick)[/{COLOR}]  Show page-picker popup

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]PLAYBACK[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [{COLOR}]w[/{COLOR}]              Watch video (best quality)
  [{COLOR}]W[/{COLOR}]              Watch video — pick quality first
  [{COLOR}]l[/{COLOR}]              Listen (audio-only, in-TUI player)
  [{COLOR}]L[/{COLOR}]              Listen — pick quality first

  [dim]During audio playback (embedded in action bar — browse freely while listening):[/dim]
  [{COLOR}]Space[/{COLOR}]          Pause / Resume
  [{COLOR}]h[/{COLOR}]              Seek back 5 seconds
  [{COLOR}]l[/{COLOR}]              Seek forward 5 seconds  [dim](replaces Listen action)[/dim]
  [{COLOR}]H[/{COLOR}]              Seek back 10 seconds
  [{COLOR}]L[/{COLOR}]              Seek forward 10 seconds  [dim](replaces Listen Quality)[/dim]
  [{COLOR}]0–9[/{COLOR}]            Seek to 0% / 10% / … / 90% of track
  [{COLOR}]s[/{COLOR}]              Stop audio  [dim](replaces Subscribe action)[/dim]

  [dim]During video playback (mpv window, same bindings):[/dim]
  [{COLOR}]h / l[/{COLOR}]          ±5 seconds
  [{COLOR}]H / L[/{COLOR}]          ±10 seconds
  [{COLOR}]0–9[/{COLOR}]            Seek to 0% / 10% / … / 90%
  [{COLOR}]q[/{COLOR}]              Quit mpv

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]DOWNLOADS & ACTIONS[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [{COLOR}]d[/{COLOR}]              Download video to Library
  [{COLOR}]a[/{COLOR}]              Download audio (MP3) to Library
  [{COLOR}]s[/{COLOR}]              Open channel page in browser (subscribe)
  [{COLOR}]p[/{COLOR}]              Add video to a playlist
  [{COLOR}]b[/{COLOR}]              Open video in browser
  [{COLOR}]r[/{COLOR}]              Refresh current feed (clears cache)

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]SEARCH & MISC[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [{COLOR}]/[/{COLOR}]              Open search dialog
  [{COLOR}]?[/{COLOR}]              Toggle this Help screen
  [{COLOR}],[/{COLOR}]              Open Settings (theme, quality, …)
  [{COLOR}]Ctrl+D[/{COLOR}]         Toggle debug log panel
  [{COLOR}]q[/{COLOR}]              Quit TermTube

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]LAZY LOADING[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  Results stream in batches of 20. Scroll near the bottom to
  automatically load the next batch — no manual action needed.

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]CONFIGURATION  (TermTube.yaml)[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [{COLOR}]browser[/{COLOR}]           chrome / firefox / brave  (for yt-dlp auth)
  [{COLOR}]cookies_file[/{COLOR}]      Path to Netscape cookies.txt (takes priority)
  [{COLOR}]preferred_quality[/{COLOR}] best / 1080 / 720 / 480 / 360
  [{COLOR}]thumbnail_format[/{COLOR}]  auto (default) / symbols / ascii
                       auto/symbols = high-quality Unicode block art (always works)
                       ascii = restrict to ASCII symbols (most compatible)
  [{COLOR}]thumbnail_cols[/{COLOR}]    Width in chars for thumbnail preview (default 38)
  [{COLOR}]video_dir[/{COLOR}]         Download directory for videos
  [{COLOR}]audio_dir[/{COLOR}]         Download directory for audio files

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [dim]Press [bold]?[/bold], [bold]q[/bold] or [bold]Esc[/bold] to close this screen.[/dim]
"""


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
        content = _HELP_CONTENT.format(COLOR=color)

        with Vertical(id="help-outer"):
            with ScrollableContainer(id="help-scroll"):
                yield Static(content, id="help-content", markup=True)

    def on_mount(self) -> None:
        self.query_one("#help-outer").border_title = "❓ Help & Keyboard Reference"

    def action_close(self) -> None:
        self.dismiss(None)
