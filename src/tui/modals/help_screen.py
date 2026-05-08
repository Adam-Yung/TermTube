"""TermTube v2 — HelpScreen.

Full-screen keyboard reference overlay.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Markdown, Static


_HELP_TEXT = """\
# TermTube v2 — Keyboard Reference

## Navigation
| Key | Action |
|-----|--------|
| ↑ / ↓  or  j / k | Move cursor up/down |
| g | Jump to top of list |
| G | Jump to bottom of list |
| ← / → | Previous / next page |
| Tab | Switch focus between list and detail panel |
| 1–5 | Switch feed tab (Home, Subscriptions, Search, Library, History) |
| / | Open search |
| r | Refresh current feed |
| Escape | Close modal / cancel |

## Playback
| Key | Action |
|-----|--------|
| l | Play audio (listen) — or seek +5s while already playing |
| w | Play video (mpv window) |
| Space | Pause / resume audio |
| h | Seek −5s |
| H | Seek −30s |
| L | Seek +30s |
| [ / ] | Volume down / up |
| s | Stop playback |
| m | Add bookmark at current position |
| B | Jump to bookmark (list dialog) |

## Actions
| Key | Action |
|-----|--------|
| Enter | Open action menu |
| d | Download video |
| a | Download audio |
| p | Add to playlist |
| x | Hide video |
| c | Copy video URL |
| o | Open in browser |
| C | Go to channel |

## App
| Key | Action |
|-----|--------|
| S | Settings |
| K | Cookie manager |
| ? | This help screen |
| q | Quit |
"""


class HelpScreen(ModalScreen[None]):
    """Keyboard shortcut reference overlay."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("?", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-box {
        width: 80%;
        max-width: 100;
        height: 80%;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        overflow-y: auto;
    }
    Markdown {
        background: transparent;
    }
    """

    def compose(self) -> ComposeResult:
        with Static(id="help-box"):
            yield Markdown(_HELP_TEXT)
