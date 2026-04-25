"""ActionBar — bottom-right panel with two modes: action hints and now-playing."""

from __future__ import annotations

from rich.table import Table
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


def _get_actions_table() -> Table:
    """Returns a borderless Rich Table to perfectly align shortcut columns."""
    # Table.grid creates a layout table with no borders.
    # padding=(0, 4) adds 4 spaces horizontally between columns.
    table = Table.grid(padding=(0, 4))
    
    # We need 5 columns for our actions
    for _ in range(5):
        table.add_column()

    # Helper functions to replicate the exact colors from your original CSS
    def r1(k: str, v: str) -> str:
        return f"[#cccccc][bold #ff6666]{k}[/bold #ff6666] [dim]{v}[/dim][/#cccccc]"

    def r2(k: str, v: str) -> str:
        return f"[#888888][bold #ff6666]{k}[/bold #ff6666] [dim]{v}[/dim][/#888888]"

    # Watch and Playlist are now vertically aligned in column 2, etc.
    table.add_row(
        r1("⏎", "Video actions"),
        r1("w", "Watch"),
        r1("l", "Listen"),
        r1("d", "DL Video"),
        r1("a", "DL Audio")
    )
    table.add_row(
        r2("s", "Subscribe"),
        r2("p", "Playlist"),
        r2("b", "Browser"),
        r2("r", "Refresh"),
        r2("?", "Help")
    )
    
    return table


_NP_KEYS = (
    "[dim]spc[/dim] pause  "
    "[bold #ff6666]h[/bold #ff6666][dim]/[/dim][bold #ff6666]l[/bold #ff6666] [dim]±5s[/dim]  "
    "[bold #ff6666]H[/bold #ff6666][dim]/[/dim][bold #ff6666]L[/bold #ff6666] [dim]±10s[/dim]  "
    "[dim]0–9[/dim] seek%  "
    "[bold #ff6666]s[/bold #ff6666] [dim]stop[/dim]"
)


def _fmt_secs(s: float) -> str:
    s = int(s)
    m, sec = divmod(s, 60)
    h, m2 = divmod(m, 60)
    if h:
        return f"{h}:{m2:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _text_bar(pos: float, dur: float, width: int) -> str:
    """Render a Unicode block progress bar of the given character width."""
    width = max(4, width)
    if dur <= 0:
        return f"[#2a2a40]{'─' * width}[/#2a2a40]"
    frac = min(pos / dur, 1.0)
    filled = int(frac * width)
    empty = width - filled
    return (
        f"[#6666ff]{'█' * filled}[/#6666ff]"
        f"[#2a2a40]{'░' * empty}[/#2a2a40]"
    )


class ActionBar(Widget):
    """
    Dual-mode bottom panel:
      • Actions mode  — keyboard shortcut grid
      • Player mode   — embedded now-playing bar with full-width text progress bar
    """

    _HEIGHT_ACTIONS = 7   # border(2) + margin-top(1) + table(2) + slack(2)
    _HEIGHT_PLAYER  = 10  # border(2) + margin-top(1) + title(1) + gap(1) + bar(1) + gap(1) + time(1) + keys(1) + slack(1)

    DEFAULT_CSS = """
    ActionBar {
        height: 7;
        background: #0d0d14;
        border: solid #2a2a2a;
        border-title-color: #555555;
        border-title-style: dim;
        margin: 0 1 1 1;
        padding: 0 1;
    }
    ActionBar > Static { height: 1; }
    
    /* The action table requires height: 2 to accommodate both rows */
    #ab-actions { height: 2; margin-top: 1; margin-left: 2; }
    
    #np-title-line { margin-top: 1; color: #ffffff; }
    #np-bar-text   { margin-top: 1; color: #6666ff; }
    #np-time-line  { color: #666666; }
    #np-keys       { margin-top: 1; color: #888888; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pos: float = 0.0
        self._dur: float = 0.0
        self._paused: bool = False
        self._title: str = ""
        self._channel: str = ""
        self._playing: bool = False

    def compose(self) -> ComposeResult:
        # ── Actions mode ──────────────────────────────────────────────────────
        # Yield the Rich Table as a single Static widget
        yield Static(_get_actions_table(), id="ab-actions")
        
        # ── Player mode (initially hidden) ────────────────────────────────────
        yield Static("", id="np-title-line", markup=True)
        yield Static("", id="np-bar-text",   markup=True)   # text-based bar
        yield Static("", id="np-time-line",  markup=True)
        yield Static(_NP_KEYS, id="np-keys", markup=True)

    def on_mount(self) -> None:
        self.border_title = "Actions"
        self._set_mode_actions()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_actions_mode(self) -> None:
        self._playing = False
        self._set_mode_actions()

    def set_player_mode(self, entry: dict) -> None:
        self._title   = (entry.get("title") or "Unknown")[:52]
        self._channel = entry.get("uploader") or entry.get("channel") or ""
        self._playing = True
        self._paused  = False
        self._pos = 0.0
        self._dur = 0.0
        self._set_mode_player()

    def update_progress(self, pos: float, dur: float, paused: bool) -> None:
        if not self._playing:
            return
        self._pos    = pos
        self._dur    = dur
        self._paused = paused
        self._refresh_player()

    # ── Private ───────────────────────────────────────────────────────────────

    def _set_mode_actions(self) -> None:
        self.styles.height = self._HEIGHT_ACTIONS
        self.border_title = "Actions"
        self.query_one("#ab-actions").display    = True
        self.query_one("#np-title-line").display = False
        self.query_one("#np-bar-text").display   = False
        self.query_one("#np-time-line").display  = False
        self.query_one("#np-keys").display       = False

    def _set_mode_player(self) -> None:
        self.styles.height = self._HEIGHT_PLAYER
        self.border_title = "Now Playing"
        self.query_one("#ab-actions").display    = False
        self.query_one("#np-title-line").display = True
        self.query_one("#np-bar-text").display   = True
        self.query_one("#np-time-line").display  = True
        self.query_one("#np-keys").display       = True
        self._refresh_player()

    def _refresh_player(self) -> None:
        # Title line
        paused_tag = "  [dim bold][PAUSED][/dim bold]" if self._paused else ""
        chan = f"  [dim]· {self._channel}[/dim]" if self._channel else ""
        self.query_one("#np-title-line", Static).update(
            f"[bold white]🎵  {self._title}[/bold white]{chan}{paused_tag}"
        )

        # Full-width text bar.
        # Available inner width = widget width - 2 (border) - 2 (padding L+R).
        inner_w = max(8, (self.size.width or 60) - 4)
        self.query_one("#np-bar-text", Static).update(
            _text_bar(self._pos, self._dur, inner_w)
        )

        # Time
        if self._dur > 0:
            elapsed  = _fmt_secs(self._pos)
            total    = _fmt_secs(self._dur)
            pct      = int(min(self._pos / self._dur, 1.0) * 100)
            time_str = f"{elapsed}  /  {total}  ({pct}%)"
        else:
            time_str = "Loading…"
        self.query_one("#np-time-line", Static).update(f"[dim]{time_str}[/dim]")
