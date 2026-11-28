"""The channel page's tabs: widget ids, content kinds and labels."""

from __future__ import annotations

TAB_LABELS = {
    "videos": "channel_screen.tab_videos",
    "shorts": "channel_screen.tab_shorts",
    "live": "channel_screen.tab_live",
    "playlists": "channel_screen.tab_playlists",
}
TAB_KINDS = {f"ch-tab-{kind}": kind for kind in TAB_LABELS}
