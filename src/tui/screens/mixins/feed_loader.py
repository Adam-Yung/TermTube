from __future__ import annotations

import threading

from textual import work

from src import logger
from src.cookies import resolve_browser
from src.entries import Entry
from src.errors import ExtractionFailed, SourceError, classify
from src.tui.fmt import fmt_day_group
from src.tui.screens.mixins.library_rail import ACCOUNT_VIEWS, LIBRARY_VIEWS, PLAYLIST_VIEW
from src.tui.widgets.video_list import VideoListPanel

BATCH_FETCH_COUNT = 80
FIRST_BATCH_COUNT = 15
SEARCH_FETCH_COUNT = 50

FEED_TABS = ("home",)
PAGED_TABS = ("home", "search", *ACCOUNT_VIEWS)
CHANNEL_TABS = ("subscriptions",)

_loading = threading.local()
"""Per loader thread: the ``_feed_session`` its view started under (read by ``_ui``)."""

_NEEDS_BROWSER = (
    "This list needs a signed-in browser. The browser setting is none or no browser was found: "
    "pick one in Settings (,)."
)
_EMPTY_ACCOUNT = {
    "yt_history": "Nothing here. Is watch history paused on this account?",
    "yt_watchlater": "Nothing here. Is Watch Later empty?",
}
_ACCOUNT_TITLES = {"yt_history": "YouTube history", "yt_watchlater": "Watch Later"}


def _day_label(entry: Entry) -> str:
    return fmt_day_group(entry.get("watched_at"))


def _library_matcher(entries: list[Entry], query: str) -> list[Entry]:
    from src import library_query, playlist

    return library_query.rank(entries, query, playlist.membership)


def _matcher_for(view: str):
    """The filter for a view: Library views understand `key:value` tokens, other views plain text."""
    return _library_matcher if view in LIBRARY_VIEWS or view.startswith(PLAYLIST_VIEW) else None


def feed_key_of(view: str) -> str | None:
    """The yt-dlp feed key of a view backed by a feed (Home, an account source), else None."""
    return ACCOUNT_VIEWS.get(view) or (view if view in FEED_TABS else None)


def _tag_yt(entries: list[Entry]) -> list[Entry]:
    """Copies of account rows marked `_yt` (they show the YT badge); the cached originals stay untouched."""
    return [{**e, "_yt": True} for e in entries]


def _pages_for(count: int, page_size: int) -> int:
    return -(-count // page_size)


class FeedLoaderMixin:
    """Loads each tab's entries into the ``VideoListPanel`` and keeps paging ahead of the user.

    Needs ``_current_tab``, ``_search`` (a ``SearchStack``), ``_feed_session``, ``_log``, ``_worker_start`` and
    ``_worker_end`` from the screen, plus ``_show_empty_feed_modal`` and ``_prompt_ytdlp_update``.
    Tab loads run in the exclusive ``feed_loader`` group and paging in ``feed_extend``, so neither cancels
    the other; ``_feed_session`` makes any result (load or paging) from before a view change a no-op.
    """

    def _load_view(self, view: str) -> None:
        self._log(f"[dim]Loading {view}…[/dim]")
        self._list().clear_and_set_loading()
        self._list().set_matcher(_matcher_for(view))
        detail = self._detail()
        detail.clear()
        if view not in CHANNEL_TABS:
            detail.set_video_mode()
        self._start_view(view)

    def _start_view(self, view: str) -> None:
        self._feed_session += 1
        self._stream_view(view, self._feed_session)

    def _ui(self, fn, *args, **kwargs):
        """Run ``fn`` on the UI thread from a loader thread, unless the view that loader began for is gone."""
        session = _loading.session

        def run():
            if session == self._feed_session:
                return fn(*args, **kwargs)

        return self.app.call_from_thread(run)

    @work(thread=True, exclusive=True, group="feed_loader")
    def _stream_view(self, view: str, session: int) -> None:
        _loading.session = session
        panel = self._list()
        self._worker_start()
        try:
            if view in FEED_TABS:
                self._load_feed(view, panel)
            elif view in ACCOUNT_VIEWS:
                self._load_account_feed(view, panel)
            elif view in CHANNEL_TABS:
                self._load_subscriptions(panel)
            elif view == "search":
                self._load_search(panel)
            elif view == "history":
                from src import history

                recent = self._history_sort == "recent"
                self._ui(
                    lambda: panel.set_view_options(group_by=_day_label if recent else None, show_count=True)
                )
                self._load_simple_list(panel, history.ordered(history.all_entries(), self._history_sort))
            elif view == "following":
                self._load_following(panel)
            elif view in LIBRARY_VIEWS or view.startswith(PLAYLIST_VIEW):
                self._load_collection(view, panel)
        except Exception as exc:
            self._report_failure(view, panel, exc)
        finally:
            self._worker_end()

    def _report_failure(self, view: str, panel: VideoListPanel, exc: Exception) -> None:
        """Show the typed message for a failed load; the update prompt only for a real extraction failure."""
        msg = str(exc)
        err = classify(exc)
        if isinstance(err, ExtractionFailed):
            if isinstance(exc, SourceError) and view in FEED_TABS:
                self._ui(self._prompt_ytdlp_update, view, msg)
            else:
                self._ui(panel.set_error_message, f"⚠ {err.message if isinstance(exc, SourceError) else msg}")
        else:
            self._ui(panel.set_error_message, f"⚠ {err.message}")
        self._ui(self._log, f"[red]Error in {view}: {msg}[/red]")

    def _show_pages(self, panel: VideoListPanel, entries: list[Entry], *, evict: bool = True) -> None:
        call = self._ui
        call(lambda: panel.add_entries(1, entries, evict=evict))
        call(lambda: panel.load_page(1, focus=not self._rail_focused()))
        call(panel.finish_loading)

    def _load_account_feed(self, view: str, panel: VideoListPanel) -> None:
        """A read-only History source from the account: needs a browser, else the same loader as Home."""
        if resolve_browser(self.app.config) is None:
            self._ui(panel.set_empty_message, _NEEDS_BROWSER)
            return
        feed_key = ACCOUNT_VIEWS[view]
        self._ui(panel.set_breadcrumb, f"{_ACCOUNT_TITLES[feed_key]} (read-only; Y switches source)")
        self._load_feed(feed_key, panel)

    def _load_feed(self, feed_key: str, panel: VideoListPanel) -> None:
        """Show the stash instantly, then either serve the disk cache or fetch from yt-dlp.

        The stash is page 1 of the last session. Fresh entries start at page 2 so the
        first screen never changes under the cursor.
        """
        import src.ytdlp as ytdlp

        cache = self.app.cache
        call = self._ui

        account = feed_key in ACCOUNT_VIEWS.values()

        def visible(entries: list[Entry]) -> list[Entry]:
            if account:
                return _tag_yt(entries)
            if feed_key != "home":
                return entries
            return [e for e in entries if not cache.is_suppressed(e.get("id", ""))]

        stash = visible(cache.get_home_stash() or []) if feed_key == "home" else []
        stash_ids = {e["id"] for e in stash if e.get("id")}
        if stash:
            self._show_pages(panel, stash)
            logger.stage("stash shown")
            self._eager_prefetch(stash[0])
        first_page = 2 if stash else 1

        if stash and self._show_cached_feed(feed_key, panel, stash_ids, visible):
            return

        shown_ids: set[str] = set()
        pages_used = 0

        def on_first_batch(entries: list[Entry]) -> None:
            nonlocal pages_used
            batch = visible(entries)
            if not batch:
                return
            shown_ids.update(e["id"] for e in batch if e.get("id"))
            pages_used = _pages_for(len(batch), panel.page_size)
            call(panel.add_entries, first_page, batch)
            if not stash:
                call(panel.load_page, 1)
                self._eager_prefetch(batch[0])
            call(panel.finish_loading)

        fetched = visible(
            ytdlp.fetch_page_batch(
                ytdlp.FEED_URLS[feed_key],
                self.app.config,
                cache,
                skip_ids=stash_ids,
                count=BATCH_FETCH_COUNT,
                feed_key=feed_key,
                on_first_batch=on_first_batch,
                first_batch_size=FIRST_BATCH_COUNT,
                auth=True,
            )
        )
        if not fetched and not stash:
            if account:
                call(panel.set_empty_message, _EMPTY_ACCOUNT[feed_key])
            else:
                call(self._show_empty_feed_modal, feed_key)
            return

        if pages_used:
            rest = [e for e in fetched if e.get("id") not in shown_ids]
            if rest:
                call(panel.add_entries, first_page + pages_used, rest)
        else:
            call(panel.add_entries, first_page, fetched)
            if not stash:
                call(panel.load_page, 1)
            call(panel.finish_loading)

        try:
            cache.prune_video_cache_fifo(100)
        except Exception as exc:
            logger.debug("video cache prune: %s", exc)

    def _show_cached_feed(self, feed_key: str, panel: VideoListPanel, stash_ids: set[str], visible) -> bool:
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
        config = self.app.config

        def run() -> None:
            import src.ytdlp as ytdlp

            try:
                ytdlp.prefetch_stream_url(vid, config)
            except Exception as exc:
                logger.debug("eager prefetch %s: %s", vid, exc)

        threading.Thread(target=run, daemon=True, name="eager-prefetch").start()

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

    def _load_subscriptions(self, panel: VideoListPanel) -> None:
        import src.ytdlp as ytdlp

        entries = ytdlp.fetch_subscribed_channels(self.app.config, self.app.cache)
        if not entries:
            self._ui(self._show_empty_feed_modal, "subscriptions")
            return
        self._ui(self._detail().set_channel_mode)
        self._show_pages(panel, entries)

    def _load_following(self, panel: VideoListPanel) -> None:
        from src import channel_bookmarks

        entries = channel_bookmarks.entries()
        if not entries:
            self._ui(panel.set_empty_message, "No channels followed here yet. Press B on a channel page.")
            return
        self._ui(self._detail().set_channel_mode)
        self._show_pages(panel, entries, evict=False)

    def _load_search(self, panel: VideoListPanel) -> None:
        import src.ytdlp as ytdlp

        if not self._search.query:
            self._ui(panel.set_empty_message, "Press / to search")
            return
        call = self._ui
        shown: list[Entry] = []

        def on_first_batch(entries: list[Entry]) -> None:
            shown.extend(entries)
            call(panel.add_entries, 1, entries)
            call(panel.load_page, 1)
            call(panel.finish_loading)

        entries = ytdlp.fetch_search_batch(
            self._search.query, self.app.config, self.app.cache,
            count=SEARCH_FETCH_COUNT, on_first_batch=on_first_batch,
            sort=self._search.sort, kind=self._search.kind,
        )
        if not shown:
            self._show_pages(panel, entries)
        else:
            shown_ids = {e.get("id") for e in shown}
            rest = [e for e in entries if e.get("id") not in shown_ids]
            if rest:
                call(panel.add_entries, 1 + _pages_for(len(shown), panel.page_size), rest)
        if entries:
            call(self._finish_search_load, panel)

    def _finish_search_load(self, panel: VideoListPanel) -> None:
        """Back to the page and row the user left this search on (when they are held), and the back hint."""
        page, focus_id = self._search.take_position()
        if page > 1 or focus_id:
            panel.load_page(page, focus_id=focus_id)
        panel.set_breadcrumb(self._search.breadcrumb())

    def _load_simple_list(self, panel: VideoListPanel, entries: list[Entry]) -> None:
        if not entries:
            self._ui(panel.set_empty_message, "No items")
            return
        self._show_pages(panel, entries, evict=False)

    def _load_collection(self, view: str, panel: VideoListPanel) -> None:
        """A Library collection or a playlist. Library loads also refresh the rail's counts."""
        if view.startswith(PLAYLIST_VIEW):
            if not (entries := self._collection_entries(view)):
                self._ui(panel.set_empty_message, "This playlist is empty. Press p on a video to add it.")
                return
        else:
            from src import library

            config = self.app.config
            self._ui(self._set_library_counts, library.counts(library.all_entries(config.video_dir, config.audio_dir)))
            entries = self._collection_entries(view)
        self._load_simple_list(panel, entries)

    def _can_extend(self) -> bool:
        """Feeds grow only when the list shows the full set: a filter works on what is loaded."""
        return self._current_tab in PAGED_TABS and not self._list().filter_active

    def _on_last_page_reached(self) -> None:
        if self._can_extend():
            self._extend_feed(show=False, session=self._feed_session)

    def _on_past_last_page(self) -> None:
        if self._can_extend():
            self._extend_feed(show=True, session=self._feed_session)

    @work(thread=True, exclusive=True, group="feed_extend")
    def _extend_feed(self, *, show: bool, session: int) -> None:
        """Fetch the next batch of pages. With ``show`` the user is waiting on it. Dropped if the view changed."""
        panel = self._list()
        call = self.app.call_from_thread
        if show:
            call(panel.show_next_page_loading)
        self._worker_start()
        try:
            entries = self._fetch_next_batch(panel)
            if entries:
                call(self._apply_extension, session, panel, entries, show)
            elif show:
                call(self._finish_extension, session, panel)
        except Exception as exc:
            logger.debug("extend feed: %s", exc)
            if show:
                call(self._finish_extension, session, panel)
        finally:
            self._worker_end()

    def _fetch_next_batch(self, panel: VideoListPanel) -> list[Entry]:
        import src.ytdlp as ytdlp

        config, cache, tab = self.app.config, self.app.cache, self._current_tab
        skip = panel.seen_ids
        if feed_key := feed_key_of(tab):
            entries = ytdlp.fetch_page_batch(
                ytdlp.FEED_URLS[feed_key], config, cache,
                skip_ids=skip, count=BATCH_FETCH_COUNT, feed_key=None, auth=True,
            )
            if tab in ACCOUNT_VIEWS:
                return _tag_yt(entries)
            if tab == "home":
                entries = [e for e in entries if not cache.is_suppressed(e.get("id", ""))]
            return entries
        if tab == "search" and self._search.query:
            count = min(SEARCH_FETCH_COUNT, ytdlp.MAX_SEARCH_RESULTS - len(skip))
            if count <= 0:
                return []
            return ytdlp.fetch_search_batch(
                self._search.query, config, cache, skip_ids=skip, count=count,
                sort=self._search.sort, kind=self._search.kind,
            )
        return []

    def _finish_extension(self, session: int, panel: VideoListPanel) -> None:
        if session == self._feed_session:
            panel.finish_loading()

    def _apply_extension(self, session: int, panel: VideoListPanel, entries: list[Entry], show: bool) -> None:
        if session == self._feed_session:
            self._append_pages(panel, entries, show)

    @staticmethod
    def _append_pages(panel: VideoListPanel, entries: list[Entry], show: bool) -> None:
        first = panel.next_page_number
        panel.add_entries(first, entries)
        if show and not panel.load_page(first):
            panel.finish_loading()
