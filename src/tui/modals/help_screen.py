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
| j / k | Move cursor up/down |
| J / K | Next / previous page |
| g / G | Jump to top / bottom of list |
| F1–F5 | Switch tab (Home, Subs, Search, Library, History) |
| / | Open search |
| r | Refresh current feed |
| R | Hard refresh (clear cache) |
| Escape | Close modal / cancel |

## Playback
| Key | Action |
|-----|--------|
| l | Play audio (listen) — or seek +5s while playing |
| L | Seek +30s while playing — or listen with quality picker |
| w | Play video (mpv window) |
| W | Play video with quality picker |
| Space | Pause / resume |
| h | Seek −5s |
| H | Seek −30s |
| 0–9 | Seek to 0%–90% |
| [ / ] | Volume down / up |
| s | Stop playback + clear queue |
| m | Add bookmark at current position |
| B | Jump to bookmark (list dialog) |
| e | Enqueue focused video |
| > | Skip to next in queue |

## Actions
| Key | Action |
|-----|--------|
| Enter | Open action menu |
| d | Download video |
| a | Download audio |
| p | Add to playlist |
| x | Hide video from feed |
| y | Copy video URL |
| b | Open in browser |
| c | Channel drilldown |

## App
| Key | Action |
|-----|--------|
| , | Settings |
| ? | This help screen |
| Ctrl+D | Toggle debug log |
| q | Quit |
"""


class HelpScreen(ModalScreen[None]):
    """Keyboard shortcut reference overlay."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("?", "dismiss", "Close"),
        Binding("/", "focus_search", "Search", show=False),
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
    #help-search {
        margin-bottom: 1;
    }
    Markdown {
        background: transparent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._full_text = _HELP_TEXT

    def compose(self) -> ComposeResult:
        from textual.widgets import Input
        with Static(id="help-box"):
            yield Input(placeholder="Filter shortcuts…", id="help-search")
            yield Markdown(self._full_text)

    def on_input_changed(self, event) -> None:
        query = event.value.strip().lower()
        if not query:
            self.query_one(Markdown).update(self._full_text)
            return
        lines = self._full_text.splitlines()
        filtered = []
        current_header = ""
        for line in lines:
            if line.startswith("#"):
                current_header = line
            elif line.startswith("|") and query in line.lower():
                if current_header and current_header not in filtered:
                    filtered.append(current_header)
                    filtered.append("|-----|--------|")
                filtered.append(line)
        self.query_one(Markdown).update("\n".join(filtered) if filtered else "No matches.")

    def action_focus_search(self) -> None:
        from textual.widgets import Input
        self.query_one("#help-search", Input).focus()
