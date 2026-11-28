from __future__ import annotations

import threading
from collections.abc import Callable
from functools import partial

from textual import work
from textual._context import NoActiveAppError

from src import logger
from src.cookies import resolve_browser
from src.entries import Entry
from src.errors import ExtractionFailed, SourceError, classify
from src.strings import text
from src.tui.fmt import escape_markup
from src.tui.screens.mixins.feed_paging import FeedPagingMixin
from src.tui.screens.mixins.feed_rows import BATCH_FETCH_COUNT, FIRST_BATCH_COUNT, pages_for, tag_yt
from src.tui.screens.mixins.list_sources import ListSourcesMixin, matcher_for
from src.tui.views import ACCOUNT_VIEWS, CHANNEL_TABS, FEED_TABS
from src.tui.widgets.video_list import VideoListPanel

_MIN_CACHED_FEED = 15

_loading = threading.local()
"""Per loader thread: the ``_feed_session`` its view started under (read by ``_ui``)."""

_EMPTY_ACCOUNT = {
    "yt_history": "feed_loader.empty_yt_history",
    "yt_watchlater": "feed_loader.empty_watch_later",
}
_ACCOUNT_TITLES = {"yt_history": "feed_loader.title_yt_history", "yt_watchlater": "feed_loader.title_watch_later"}

Visible = Callable[[list[Entry]], list[Entry]]


class _ProgressiveFetch:
    """Shows a feed's first batch while the rest of the fetch runs, then adds the remainder after it."""

    def __init__(self, call, panel: VideoListPanel, visible: Visible, *, stash_shown: bool, prefetch) -> None:
        self._call = call
        self._panel = panel
        self._visible = visible
        self._stash_shown = stash_shown
        self._prefetch = prefetch
        self._first_page = 2 if stash_shown else 1
        self._shown_ids: set[str] = set()
        self._pages_used = 0

    def on_first_batch(self, entries: list[Entry]) -> None:
        batch = self._visible(entries)
        if not batch:
            return
        self._shown_ids.update(e["id"] for e in batch if e.get("id"))
        self._pages_used = pages_for(len(batch), self._panel.page_size)
        self._call(self._panel.add_entries, self._first_page, batch)
        if not self._stash_shown:
            self._call(self._panel.load_page, 1)
            self._prefetch(batch[0])
        self._call(self._panel.finish_loading)

    def add_rest(self, fetched: list[Entry]) -> None:
        if self._pages_used:
            rest = [e for e in fetched if e.get("id") not in self._shown_ids]
            if rest:
                self._call(self._panel.add_entries, self._first_page + self._pages_used, rest)
            return
        self._call(self._panel.add_entries, self._first_page, fetched)
        if not self._stash_shown:
            self._call(self._panel.load_page, 1)
        self._call(self._panel.finish_loading)


class FeedLoaderMixin(ListSourcesMixin, FeedPagingMixin):
    """Loads each tab's entries into the ``VideoListPanel`` and keeps paging ahead of the user.

    Needs ``_current_tab``, ``_search`` (a ``SearchStack``), ``_feed_session``, ``_log``, ``_worker_start`` and
    ``_worker_end`` from the screen, plus ``_show_empty_feed_modal``, ``_prompt_ytdlp_update`` and
    ``_cancel_removal_prompt``. Home and account feeds load here; the other views in ``ListSourcesMixin``.
    Tab loads run in the exclusive ``feed_loader`` group and paging in ``feed_extend``, so neither cancels
    the other; ``_feed_session`` makes any result (load or paging) from before a view change a no-op.
    """

    _feed_cursor = None
    _show_played = False
    _hidden_ids: set[str] = set()

    def _load_view(self, view: str) -> None:
        self._log(f"[dim]Loading {view}…[/dim]")
        self._list().clear_and_set_loading()
        self._list().set_matcher(matcher_for(view))
        detail = self._detail()
        detail.clear()
        if view not in CHANNEL_TABS:
            detail.set_video_mode()
        self._start_view(view)

    def _start_view(self, view: str) -> None:
        self._close_cursor()
        self._cancel_removal_prompt()
        self._feed_session += 1
        self._pending_show = False
        self._stream_view(view, self._feed_session)

    def _adopt_loader_session(self, session: int) -> None:
        """Called first thing on a loader thread: ``_ui`` calls from it are dropped once the view moved on."""
        _loading.session = session

    def _ui(self, fn, *args, **kwargs):
        """Run ``fn`` on the UI thread from a loader thread, unless the view that loader began for is gone."""
        try:
            return self.app.call_ui(self._run_for_session, _loading.session, partial(fn, *args, **kwargs))
        except NoActiveAppError:  # the app quit while this loader thread ran
            return None

    def _run_for_session(self, session: int, call: Callable):
        if session == self._feed_session:
            return call()

    @work(thread=True, exclusive=True, group="feed_loader")
    def _stream_view(self, view: str, session: int) -> None:
        self._adopt_loader_session(session)
        panel = self._list()
        self._worker_start()
        try:
            if loader := self._view_loader(view):
                loader(panel)
        except Exception as exc:
            self._report_failure(view, panel, exc)
        finally:
            self._worker_end()

    def _view_loader(self, view: str) -> Callable[[VideoListPanel], None] | None:
        if view in FEED_TABS:
            return partial(self._load_feed, view)
        if view in ACCOUNT_VIEWS:
            return partial(self._load_account_feed, view)
        return self._source_loader(view)

    def _report_failure(self, view: str, panel: VideoListPanel, exc: Exception) -> None:
        """Show the typed message for a failed load; the update prompt only for a real extraction failure."""
        msg = str(exc)
        err = classify(exc)
        if isinstance(err, ExtractionFailed):
            if isinstance(exc, SourceError) and view in FEED_TABS:
                self._ui(self._prompt_ytdlp_update, view, msg)
            else:
                shown = err.message if isinstance(exc, SourceError) else msg
                self._ui(panel.set_error_message, text("feed_loader.error", message=shown))
        else:
            self._ui(panel.set_error_message, text("feed_loader.error", message=err.message))
        self._ui(self._log, f"[red]Error in {view}: {escape_markup(msg)}[/red]")

    def _load_account_feed(self, view: str, panel: VideoListPanel) -> None:
        """A read-only History source from the account: needs a browser, else the same loader as Home."""
        if resolve_browser(self.app.config) is None:
            self._ui(panel.set_empty_message, text("feed_loader.needs_browser"))
            return
        feed_key = ACCOUNT_VIEWS[view]
        self._ui(panel.set_breadcrumb, text("feed_loader.account_crumb", title=text(_ACCOUNT_TITLES[feed_key])))
        self._load_feed(feed_key, panel)

    def _load_feed(self, feed_key: str, panel: VideoListPanel) -> None:
        """Show the stash instantly, then either serve the disk cache or fetch from yt-dlp.

        The stash is page 1 of the last session. Fresh entries start at page 2 so the
        first screen never changes under the cursor.
        """
        import src.ytdlp as ytdlp

        cache = self.app.cache
        home = feed_key == "home"
        account = feed_key in ACCOUNT_VIEWS.values()

        hidden: set[str] = set()
        if home:
            self._ui(self._reset_hidden, hidden)
        visible = partial(self._visible_rows, feed_key, hidden)

        age = cache.feed_age(feed_key) if home else None
        stale = age is not None and age > self.app.config.cache_ttl("home_revalidate")

        stash = visible(cache.get_home_stash() or []) if home else []
        stash_ids = {e["id"] for e in stash if e.get("id")}
        if stash:
            self._show_stash(panel, stash)

        if stash and self._show_cached_feed(feed_key, panel, stash_ids, visible):
            if stale:
                self._revalidate(feed_key, panel, visible)
            return

        progress = _ProgressiveFetch(
            self._ui, panel, visible, stash_shown=bool(stash), prefetch=self._eager_prefetch
        )
        cursor = self._open_cursor(feed_key)
        if cursor is None:
            return
        fetched = visible(
            ytdlp.fetch_page_batch(
                ytdlp.FEED_URLS[feed_key],
                self.app.config,
                cache,
                skip_ids=stash_ids,
                count=BATCH_FETCH_COUNT,
                feed_key=feed_key,
                on_first_batch=progress.on_first_batch,
                first_batch_size=FIRST_BATCH_COUNT,
                auth=True,
                cursor=cursor,
            )
        )
        if not fetched and not stash:
            if account:
                self._ui(panel.set_empty_message, text(_EMPTY_ACCOUNT[feed_key]))
            else:
                self._ui(self._show_empty_feed_modal, feed_key)
            return

        progress.add_rest(fetched)

        if stale and not cursor.ids:
            self._revalidate(feed_key, panel, visible)

        try:
            cache.prune_video_cache_fifo(100)
        except Exception as exc:
            logger.debug("video cache prune: %s", exc)

    def _visible_rows(self, feed_key: str, hidden: set[str], entries: list[Entry]) -> list[Entry]:
        """The rows of a feed as shown: account rows are badged, Home drops the played ones."""
        if feed_key in ACCOUNT_VIEWS.values():
            return tag_yt(entries)
        if feed_key != "home":
            return entries
        return self._hide_played(entries, hidden)

    def _show_stash(self, panel: VideoListPanel, stash: list[Entry]) -> None:
        self._show_pages(panel, stash)
        logger.stage("stash shown")
        self._eager_prefetch(stash[0])

    def _reset_hidden(self, hidden: set[str]) -> None:
        self._hidden_ids = hidden
        self._list().set_hidden(0, showing=self._show_played)

    def _hide_played(self, entries: list[Entry], hidden: set[str]) -> list[Entry]:
        """Home without the videos already played (unless Z shows them); counts the hidden ones in the footer."""
        if self._show_played:
            return entries
        suppressed = self.app.cache.is_suppressed
        kept = [e for e in entries if not suppressed(e.get("id", ""))]
        hidden.update(e.get("id", "") for e in entries if suppressed(e.get("id", "")))
        self._ui(lambda: self._list().set_hidden(len(hidden)))
        return kept

    def _revalidate(self, feed_key: str, panel: VideoListPanel, visible: Visible) -> None:
        """Stale-while-revalidate: read the feed again behind the cached rows and only announce what is new.

        The rows under the cursor never change; ``r`` reloads from the refreshed cache. Failures stay silent.
        """
        cache = self.app.cache
        try:
            cursor = self._feed_cursor or self._open_cursor(feed_key)
            if cursor is None:
                return
            fresh = visible(cursor.take(BATCH_FETCH_COUNT, set()))
            if len(cursor.ids) >= _MIN_CACHED_FEED:
                cache.put_feed(feed_key, list(cursor.ids))
            held = self._ui(lambda: panel.seen_ids)
            new = [e for e in fresh if held is not None and e.get("id") not in held]
            if new:
                self._ui(panel.set_notice, text("feed_loader.new_videos", count=len(new)))
        except Exception as exc:
            logger.debug("revalidate %s: %s", feed_key, exc)

    def _show_cached_feed(
        self, feed_key: str, panel: VideoListPanel, stash_ids: set[str], visible: Visible
    ) -> bool:
        """Fill pages 2+ from the disk cache when it is fresh. False if there was nothing to show."""
        cache = self.app.cache
        if not cache.is_feed_fresh(feed_key):
            return False
        entries: list[Entry] = []
        for vid in cache.get_feed(feed_key) or []:
            if vid in stash_ids:
                continue
            raw = cache.get_video_raw(vid)
            if raw:
                entries.extend(visible([raw]))
            if len(entries) >= BATCH_FETCH_COUNT:
                break
        if not entries:
            return False
        self._ui(panel.add_entries, 2, entries)
        logger.debug("feed %s: %d cached entries, no network", feed_key, len(entries))
        return True

    def _eager_prefetch(self, entry: Entry) -> None:
        """Resolve the first row's stream URL now so the first play starts fast."""
        vid = entry.get("id", "")
        if not vid or vid.startswith("__"):
            return
        threading.Thread(
            target=self._prefetch_first_row, args=(vid, self.app.config), daemon=True, name="eager-prefetch"
        ).start()

    @staticmethod
    def _prefetch_first_row(vid: str, config) -> None:
        from src import streams

        try:
            streams.prefetch_stream_url(vid, config)
        except Exception as exc:
            logger.debug("eager prefetch %s: %s", vid, exc)

    def _save_feed_stash(self, feed_key: str) -> None:
        """Keep one page of unseen entries for the next launch, topped up from visited pages."""
        if feed_key != "home":
            return
        try:
            panel = self._list()
            entries = panel.all_unseen_entries()
            size = panel.page_size
            if len(entries) < size:
                have = {e.get("id") for e in entries}
                visited = [e for e in panel.visited_entries() if e.get("id") not in have]
                entries += visited[-(size - len(entries)):]
            stash = entries[:size]
            if stash:
                self.app.cache.put_home_stash(stash)
                logger.debug("stash: saved %d entries", len(stash))
        except Exception as exc:
            logger.debug("stash save: %s", exc)

    def _open_cursor(self, feed_key: str):
        """A lazy listing of the feed for this view (it opens on the first ``take``). None if the view changed."""
        import src.ytdlp as ytdlp
        from src.feed_cursor import FeedCursor

        cursor = FeedCursor(
            ytdlp.FEED_URLS[feed_key], self.app.config, self.app.cache, auth=True, playlists=feed_key == "home"
        )
        if not self._ui(self._adopt_cursor, cursor):
            cursor.close()
            return None
        return cursor

    def _adopt_cursor(self, cursor) -> bool:
        self._close_cursor()
        self._feed_cursor = cursor
        return True

    def _close_cursor(self) -> None:
        cursor, self._feed_cursor = self._feed_cursor, None
        if cursor is not None:
            cursor.close()
