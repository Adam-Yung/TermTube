"""The views a list can show: their ids, which tab each belongs to and how each is loaded."""

from __future__ import annotations

LIBRARY_VIEWS = ("library", "library:video", "library:audio")
PLAYLIST_VIEW = "playlist:"
ACCOUNT_VIEWS = {"history:yt": "yt_history", "history:wl": "yt_watchlater"}
"""History-tab sources read from the account (read-only), each with its feed key."""
HISTORY_SOURCES = ("history", *ACCOUNT_VIEWS)
SUBSCRIPTION_SOURCES = ("subscriptions", "following")
RAIL_TABS = ("library", "history", "subscriptions")
"""Tabs with a left rail: each rail entry is one source of the tab."""
FEED_TABS = ("home",)
PAGED_TABS = ("home", "search", *ACCOUNT_VIEWS)
CHANNEL_TABS = ("subscriptions",)


def playlist_of(view: str) -> str | None:
    """The id of the local playlist a view shows, or None on any other view."""
    return view.removeprefix(PLAYLIST_VIEW) if view.startswith(PLAYLIST_VIEW) else None


def is_library_view(view: str) -> bool:
    """A Library collection or a local playlist."""
    return view in LIBRARY_VIEWS or view.startswith(PLAYLIST_VIEW)


def tab_of(view: str) -> str:
    """The tab a view belongs to: Library collections and playlists live on `library`, History sources on `history`."""
    if is_library_view(view):
        return "library"
    if view in SUBSCRIPTION_SOURCES:
        return "subscriptions"
    return "history" if view in HISTORY_SOURCES else view


def feed_key_of(view: str) -> str | None:
    """The yt-dlp feed key of a view backed by a feed (Home, an account source), else None."""
    return ACCOUNT_VIEWS.get(view) or (view if view in FEED_TABS else None)


def default_rail_views() -> dict[str, str]:
    """The source each rail tab opens on."""
    return {tab: tab for tab in RAIL_TABS}
