"""HelpScreen — full-page reference for all keyboard shortcuts and features."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


_HELP_CONTENT = """\
[bold #ff4444]MyYouTube — Keyboard Reference[/bold #ff4444]

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]NAVIGATION[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [#ff4444]j / ↓[/#ff4444]          Move cursor down
  [#ff4444]k / ↑[/#ff4444]          Move cursor up
  [#ff4444]g[/#ff4444]              Jump to top of list
  [#ff4444]G[/#ff4444]              Jump to bottom of list
  [#ff4444]Backspace[/#ff4444]      Go back (e.g. from playlist drill-down)
  [#ff4444]Enter[/#ff4444]          Open selected item (video or playlist)

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]PAGES  (F-keys or backtick picker)[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [#ff4444]F1[/#ff4444]             🏠  Home / Recommended
  [#ff4444]F2[/#ff4444]             📺  Subscriptions
  [#ff4444]F3[/#ff4444]             🔍  Search
  [#ff4444]F4[/#ff4444]             🕐  History
  [#ff4444]F5[/#ff4444]             📁  Library (downloaded files)
  [#ff4444]F6[/#ff4444]             🎵  Playlists
  [#ff4444]F7[/#ff4444]             ❓  Help (this screen)
  [#ff4444]`  (backtick)[/#ff4444]  Show page-picker popup

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]PLAYBACK[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [#ff4444]w[/#ff4444]              Watch video (best quality)
  [#ff4444]W[/#ff4444]              Watch video — pick quality first
  [#ff4444]l[/#ff4444]              Listen (audio-only, in-TUI player)
  [#ff4444]L[/#ff4444]              Listen — pick quality first

  [dim]During audio playback (Now Playing screen):[/dim]
  [#ff4444]Space[/#ff4444]          Pause / Resume
  [#ff4444]h / ←[/#ff4444]         Seek back 5 seconds
  [#ff4444]l / →[/#ff4444]         Seek forward 5 seconds
  [#ff4444]H[/#ff4444]              Seek back 10 seconds
  [#ff4444]L[/#ff4444]              Seek forward 10 seconds
  [#ff4444]0–9[/#ff4444]            Seek to 0% / 10% / … / 90% of track
  [#ff4444]q / Esc[/#ff4444]        Stop and close player

  [dim]During video playback (mpv window, same bindings):[/dim]
  [#ff4444]h / l[/#ff4444]          ±5 seconds
  [#ff4444]H / L[/#ff4444]          ±10 seconds
  [#ff4444]0–9[/#ff4444]            Seek to 0% / 10% / … / 90%
  [#ff4444]q[/#ff4444]              Quit mpv

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]DOWNLOADS & ACTIONS[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [#ff4444]d[/#ff4444]              Download video to Library
  [#ff4444]a[/#ff4444]              Download audio (MP3) to Library
  [#ff4444]s[/#ff4444]              Open channel page in browser (subscribe)
  [#ff4444]p[/#ff4444]              Add video to a playlist
  [#ff4444]b[/#ff4444]              Open video in browser
  [#ff4444]r[/#ff4444]              Refresh current feed (clears cache)

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]SEARCH & MISC[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [#ff4444]/[/#ff4444]              Open search dialog
  [#ff4444]?[/#ff4444]              Toggle this Help screen
  [#ff4444]Ctrl+D[/#ff4444]         Toggle debug log panel
  [#ff4444]q[/#ff4444]              Quit MyYouTube

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]LAZY LOADING[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  Results stream in batches of 20. Scroll near the bottom to
  automatically load the next batch — no manual action needed.

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]
[bold white]CONFIGURATION  (MyYouTube.yaml)[/bold white]
[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [#ff4444]browser[/#ff4444]           chrome / firefox / brave  (for yt-dlp auth)
  [#ff4444]cookies_file[/#ff4444]      Path to Netscape cookies.txt (takes priority)
  [#ff4444]preferred_quality[/#ff4444] best / 1080 / 720 / 480 / 360
  [#ff4444]thumbnail_format[/#ff4444]  auto (default) / symbols / ascii
                       auto/symbols = high-quality Unicode block art (always works)
                       ascii = restrict to ASCII symbols (most compatible)
  [#ff4444]thumbnail_cols[/#ff4444]    Width in chars for thumbnail preview (default 38)
  [#ff4444]video_dir[/#ff4444]         Download directory for videos
  [#ff4444]audio_dir[/#ff4444]         Download directory for audio files

[bold #888888]──────────────────────────────────────────────────────────────────────[/bold #888888]

  [dim]Press [bold]?[/bold], [bold]q[/bold] or [bold]Esc[/bold] to close this screen.[/dim]
"""


class HelpScreen(ModalScreen[None]):
    """Full-page keyboard reference, openable via ? or the Help tab."""

    BINDINGS = [
        Binding("?",      "close", "Close", show=True),
        Binding("q",      "close", "Close", show=False),
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

    def compose(self) -> ComposeResult:
        with Vertical(id="help-outer"):
            with ScrollableContainer(id="help-scroll"):
                yield Static(_HELP_CONTENT, id="help-content", markup=True)

    def on_mount(self) -> None:
        self.query_one("#help-outer").border_title = "❓ Help & Keyboard Reference"

    def action_close(self) -> None:
        self.dismiss(None)
