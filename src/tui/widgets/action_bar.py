"""ActionBar — bottom-right panel with two modes: action hints and now-playing."""

from __future__ import annotations

from rich.table import Table
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


def _get_actions_table() -> Table:
    table = Table.grid(padding=(0, 4))
    for _ in range(5):
        table.add_column()

    def r1(k: str, v: str) -> str:
        return f"[#cccccc][bold #ff6666]{k}[/bold #ff6666] [dim]{v}[/dim][/#cccccc]"

    def r2(k: str, v: str) -> str:
        return f"[#888888][bold #ff6666]{k}[/bold #ff6666] [dim]{v}[/dim][/#888888]"

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
    "[bold #ff6666]⎵[/bold #ff6666] [dim]pause[/dim]  "
    "[bold #ff6666]h[/bold #ff6666][dim]/[/dim][bold #ff6666]l[/bold #ff6666] [dim]±5s[/dim]  "
    "[bold #ff6666]H[/bold #ff6666][dim]/[/dim][bold #ff6666]L[/bold #ff6666] [dim]±10s[/dim]  "
    "[bold #ff6666]0[/bold #ff6666][dim]–[/dim][bold #ff6666]9[/bold #ff6666] [dim]seek%[/dim]  "
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


def _queue_hint(queue_len: int) -> str:
    if queue_len > 0:
        return (
            f"[bold #ff6666]e[/bold #ff6666] [dim]add to queue[/dim]  "
            f"[bold #ff6666]>[/bold #ff6666] [dim]skip to next  ({queue_len} queued)[/dim]"
        )
    return "[bold #ff6666]e[/bold #ff6666] [dim]add to queue[/dim]"


class ActionBar(Widget):
    """
    Dual-mode bottom panel:
      • Actions mode  — keyboard shortcut grid
      • Player mode   — embedded now-playing bar with text progress and queue hints
    """

    _HEIGHT_ACTIONS = 7
    _HEIGHT_PLAYER  = 11  # +1 for queue hint line vs original 10

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

    #ab-actions { height: 2; margin-top: 1; margin-left: 2; }

    #np-title-line { margin-top: 1; color: #ffffff; }
    #np-bar-text   { margin-top: 1; color: #6666ff; }
    #np-time-line  { color: #666666; }
    #np-keys       { margin-top: 1; color: #888888; }
    #np-queue-line { color: #888888; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pos: float = 0.0
        self._dur: float = 0.0
        self._paused: bool = False
        self._title: str = ""
        self._channel: str = ""
        self._playing: bool = False
        self._queue_len: int = 0

    def compose(self) -> ComposeResult:
        yield Static(_get_actions_table(), id="ab-actions")
        yield Static("", id="np-title-line", markup=True)
        yield Static("", id="np-bar-text",   markup=True)
        yield Static("", id="np-time-line",  markup=True)
        yield Static(_NP_KEYS, id="np-keys", markup=True)
        yield Static("", id="np-queue-line", markup=True)

    def on_mount(self) -> None:
        self.border_title = "Actions"
        self._set_mode_actions()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_actions_mode(self) -> None:
        self._playing = False
        self._queue_len = 0
        self._set_mode_actions()

    def set_player_mode(self, entry: dict, queue_len: int = 0) -> None:
        self._title   = (entry.get("title") or "Unknown")[:52]
        self._channel = entry.get("uploader") or entry.get("channel") or ""
        self._playing = True
        self._paused  = False
        self._pos = 0.0
        self._dur = 0.0
        self._queue_len = queue_len
        self._set_mode_player()

    def update_progress(self, pos: float, dur: float, paused: bool) -> None:
        if not self._playing:
            return
        self._pos    = pos
        self._dur    = dur
        self._paused = paused
        self._refresh_player()

    def update_queue_hint(self, queue_len: int) -> None:
        """Update the queue hint line while staying in player mode."""
        if not self._playing:
            return
        self._queue_len = queue_len
        self.query_one("#np-queue-line", Static).update(_queue_hint(queue_len))

    # ── Private ───────────────────────────────────────────────────────────────

    def _set_mode_actions(self) -> None:
        self.styles.height = self._HEIGHT_ACTIONS
        self.border_title = "Actions"
        self.query_one("#ab-actions").display    = True
        self.query_one("#np-title-line").display = False
        self.query_one("#np-bar-text").display   = False
        self.query_one("#np-time-line").display  = False
        self.query_one("#np-keys").display       = False
        self.query_one("#np-queue-line").display = False

    def _set_mode_player(self) -> None:
        self.styles.height = self._HEIGHT_PLAYER
        self.border_title = "Now Playing"
        self.query_one("#ab-actions").display    = False
        self.query_one("#np-title-line").display = True
        self.query_one("#np-bar-text").display   = True
        self.query_one("#np-time-line").display  = True
        self.query_one("#np-keys").display       = True
        self.query_one("#np-queue-line").display = True
        self.query_one("#np-queue-line", Static).update(_queue_hint(self._queue_len))
        self._refresh_player()

    def _refresh_player(self) -> None:
        paused_tag = "  [dim bold][PAUSED][/dim bold]" if self._paused else ""
        chan = f"  [dim]· {self._channel}[/dim]" if self._channel else ""
        self.query_one("#np-title-line", Static).update(
            f"[bold white]🎵  {self._title}[/bold white]{chan}{paused_tag}"
        )

        inner_w = max(8, (self.size.width or 60) - 4)
        self.query_one("#np-bar-text", Static).update(
            _text_bar(self._pos, self._dur, inner_w)
        )

        if self._dur > 0:
            elapsed  = _fmt_secs(self._pos)
            total    = _fmt_secs(self._dur)
            pct      = int(min(self._pos / self._dur, 1.0) * 100)
            time_str = f"{elapsed}  /  {total}  ({pct}%)"
        else:
            time_str = "Loading…"
        self.query_one("#np-time-line", Static).update(f"[dim]{time_str}[/dim]")
