from __future__ import annotations

from textual import work

from src import logger
from src.entries import Entry
from src.errors import classify
from src.strings import text
from src.tui.screens.mixins.feed_rows import BATCH_FETCH_COUNT, SEARCH_FETCH_COUNT, tag_yt
from src.tui.views import ACCOUNT_VIEWS, PAGED_TABS, feed_key_of
from src.tui.widgets.video_list import VideoListPanel


class FeedPagingMixin:
    """Fetches the next batch of a feed or search as the user nears the end of what is held.

    Needs ``_list``, ``_current_tab``, ``_search``, ``_feed_session``, ``_feed_cursor``, ``_open_cursor``,
    ``_hide_played``, ``_hidden_ids``, ``_adopt_loader_session``, ``_hint``, ``_worker_start``, ``_worker_end``
    and ``app``. Runs in the exclusive ``feed_extend`` group.
    """

    _extending_session: int | None = None
    _pending_show = False

    def _can_extend(self) -> bool:
        """Feeds grow only when the list shows the full set: a filter works on what is loaded."""
        if self._current_tab not in PAGED_TABS or self._list().filter_active:
            return False
        cursor = self._feed_cursor
        return not (cursor is not None and feed_key_of(self._current_tab) and cursor.exhausted)

    def _on_page_shown(self) -> None:
        """Prefetch: a feed grows when the user reaches its second-to-last page, Search at its last."""
        panel = self._list()
        lead = 1 if feed_key_of(self._current_tab) else 0
        if panel.current_page >= panel.total_pages - lead and not panel.is_loading and self._can_extend():
            self._request_extension(show=False)

    def _on_past_last_page(self) -> None:
        if self._can_extend():
            self._request_extension(show=True)

    def _request_extension(self, *, show: bool) -> None:
        """Start one extension, or when one is in flight only make its result show as soon as it lands."""
        panel, session = self._list(), self._feed_session
        if self._extending_session == session:
            if show and not self._pending_show:
                self._pending_show = True
                panel.show_next_page_loading()
            return
        self._extending_session = session
        more = SEARCH_FETCH_COUNT if self._current_tab == "search" else BATCH_FETCH_COUNT
        panel.set_progress(text("feed_loader.loading_more", count=more))
        self._extend_feed(show=show, session=session)

    @work(thread=True, exclusive=True, group="feed_extend")
    def _extend_feed(self, *, show: bool, session: int) -> None:
        """Fetch the next batch of pages. With ``show`` the user is waiting on it. Dropped if the view changed."""
        self._adopt_loader_session(session)
        panel = self._list()
        call = self.app.call_from_thread
        if show:
            call(self._show_waiting, session, panel)
        self._worker_start()
        try:
            entries = self._fetch_next_batch(panel)
            call(self._apply_extension, session, panel, entries, show)
        except Exception as exc:
            logger.debug("extend feed: %s", exc)
            call(self._extension_failed, session, panel, classify(exc).message)
        finally:
            self._worker_end()

    def _show_waiting(self, session: int, panel: VideoListPanel) -> None:
        if session == self._feed_session and not self._pending_show:
            self._pending_show = True
            panel.show_next_page_loading()

    def _fetch_next_batch(self, panel: VideoListPanel) -> list[Entry]:
        import src.ytdlp as ytdlp

        config, cache, tab = self.app.config, self.app.cache, self._current_tab
        skip = panel.seen_ids
        if feed_key := feed_key_of(tab):
            return self._next_feed_batch(feed_key, tab, skip)
        if tab == "search" and self._search.query:
            count = min(SEARCH_FETCH_COUNT, ytdlp.MAX_SEARCH_RESULTS - len(skip))
            if count <= 0:
                return []
            return ytdlp.fetch_search_batch(
                self._search.query, config, cache, skip_ids=skip, count=count,
                sort=self._search.sort, kind=self._search.kind,
            )
        return []

    def _next_feed_batch(self, feed_key: str, tab: str, skip: set[str]) -> list[Entry]:
        """Up to three takes from the cursor, until one yields a row that is not hidden."""
        cursor = self._feed_cursor or self._open_cursor(feed_key)
        if cursor is None:
            return []
        out: list[Entry] = []
        for _ in range(3):
            got = cursor.take(BATCH_FETCH_COUNT, skip)
            skip = skip | {e["id"] for e in got}
            if tab in ACCOUNT_VIEWS:
                got = tag_yt(got)
            elif tab == "home":
                got = self._hide_played(got, self._hidden_ids)
            out += got
            if out or cursor.exhausted or cursor.closed:
                break
        return out

    def _extension_done(self, session: int, panel: VideoListPanel) -> bool:
        """Common end of an extension on the UI thread. False when the view changed meanwhile."""
        if self._extending_session == session:
            self._extending_session = None
        if session != self._feed_session:
            return False
        panel.set_progress("")
        return True

    def _extension_failed(self, session: int, panel: VideoListPanel, message: str) -> None:
        was_waiting = self._pending_show
        if self._extension_done(session, panel):
            self._pending_show = False
            panel.set_progress(text("feed_loader.error", message=message))
            if was_waiting:
                panel.load_page(panel.total_pages, cursor="last")
                self._hint(message)

    def _apply_extension(self, session: int, panel: VideoListPanel, entries: list[Entry], show: bool) -> None:
        if not self._extension_done(session, panel):
            return
        show = show or self._pending_show
        self._pending_show = False
        if not entries:
            if show:
                panel.load_page(panel.total_pages, cursor="last")
            return
        panel.append_pages(entries, show)
        panel.set_progress(text("feed_loader.loaded_count", count=panel.loaded_count))
        self._on_page_shown()
