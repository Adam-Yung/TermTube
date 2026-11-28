from __future__ import annotations

from textual import work

from src import channel_ref, innertube, logger, playlist_fetch
from src.channel_pager import ChannelPager
from src.entries import PlaylistEntry
from src.errors import classify
from src.strings import text


class ChannelContentMixin:
    """Loads and pages the channel page's list: videos, Shorts, Live, playlists or one playlist's videos.

    Needs ``_channel_url``, ``_channel_name``, ``_playlist``, ``_solo``, ``_sort``, ``_tab_kind``, ``_list``,
    ``_info_panel``, ``_apply_playlist_info``, ``_show_breadcrumb``, ``_fetch_playlist_videos``, ``_call_ui`` and
    ``app`` from the screen, which calls ``_init_channel_content`` from ``__init__``.
    """

    def _init_channel_content(self) -> None:
        self._content_session = 0
        self._content_started = False
        self._pager = ChannelPager()
        self._resolved_id: str | None = None
        self._pending_show = False

    def _start_content_once(self) -> None:
        if not self._content_started:
            self._start_content_load()

    def _start_content_load(self) -> None:
        self._content_started = True
        self._content_session += 1
        self._pager.reset()
        self._pending_show = False
        self._list().clear_and_set_loading()
        self._show_breadcrumb()
        self._load_content(self._content_kind(), self._sort, self._content_session)

    @work(thread=True, exclusive=True, group="ch_content")
    def _load_content(self, kind: str, sort: str, session: int) -> None:
        call = self._call_ui
        try:
            page = self._fetch_first_page(kind, sort)
        except Exception as exc:
            logger.debug("channel content: %s", exc)
            page = None
            call(self._show_content_error, session, classify(exc).message)
        if page is not None:
            call(self._show_first_page, session, page)

    def _show_first_page(self, session: int, page: innertube.ChannelPage) -> None:
        if session != self._content_session:
            return
        panel = self._list()
        info = page.info
        if self._solo:
            self._apply_playlist_info(info)
        if not page.entries:
            reason = (info or {}).get("unavailable")
            panel.set_empty_message(reason or text("channel_screen.no_content"))
            return
        panel.add_entries(1, page.entries)
        panel.load_page(1)
        panel.finish_loading()
        self._pager.start(len(page.entries), page.token, (info or {}).get("video_count"))
        self._maybe_prefetch()

    def _show_content_error(self, session: int, message: str) -> None:
        if session == self._content_session:
            self._list().set_error_message(message)

    def _fetch_first_page(self, kind: str, sort: str) -> innertube.ChannelPage:
        if kind == "playlist":
            return self._fetch_playlist_videos()
        if kind == "playlists":
            return innertube.ChannelPage(self._fetch_playlists())
        if kind in ("shorts", "live"):
            return self._fetch_tab(kind)
        return self._fetch_videos(sort)

    def _fetch_tab(self, kind: str) -> innertube.ChannelPage:
        """Shorts or Live: InnerTube only. yt-dlp has no equivalent that is worth the wait."""
        channel_id = self._channel_id()
        page = innertube.fetch_channel_page(channel_id, kind) if channel_id else innertube.ChannelPage([])
        self._label(page.entries)
        return page

    def _fetch_playlists(self) -> list[PlaylistEntry]:
        """InnerTube browse (fast); yt-dlp when the id is unknown or the response is empty."""
        import src.ytdlp as ytdlp

        channel_id = self._channel_id()
        if channel_id:
            entries = innertube.fetch_channel_playlists(channel_id)
            if entries:
                return entries
            logger.debug("InnerTube channel playlists empty; falling back to yt-dlp")
        return ytdlp.fetch_channel_playlists(self._channel_url, self.app.config, self.app.cache)

    def _fetch_videos(self, sort: str) -> innertube.ChannelPage:
        """InnerTube for newest-first (fast, with a continuation); yt-dlp for other sorts or when InnerTube is empty.

        InnerTube's popular and oldest filter chips are not used (decision log 2026-11-18): the other sorts go to
        yt-dlp, which returns one batch with no continuation.
        """
        import src.ytdlp as ytdlp

        channel_id = self._channel_id()
        if channel_id and sort == "date":
            page = innertube.fetch_channel_page(channel_id, "videos")
            if page.entries:
                self._label(page.entries)
                return page
            logger.debug("InnerTube channel videos empty; falling back to yt-dlp")
        return innertube.ChannelPage(
            ytdlp.fetch_channel_videos(self._channel_url, self.app.config, self.app.cache, sort=sort)
        )

    def _label(self, entries: list) -> None:
        """InnerTube channel rows carry no channel name; the page knows it."""
        for entry in entries:
            entry.setdefault("channel", self._channel_name)
            entry.setdefault("uploader", self._channel_name)

    def _maybe_prefetch(self) -> None:
        """Fetch the next page ahead of the user: on the second-to-last held page, never while filtering."""
        panel = self._list()
        if not panel.filter_active and self._pager.wants_more(panel.current_page, panel.total_pages):
            self._extend(show=False)

    def _extend(self, *, show: bool) -> None:
        """Start the next fetch, or when one is in flight make its result show as soon as it lands."""
        panel = self._list()
        if self._pager.fetching:
            if show:
                self._pending_show = True
                panel.show_next_page_loading()
            return
        if not self._pager.token or panel.filter_active:
            return
        token = self._pager.begin_fetch()
        panel.set_progress(self._pager.note())
        if show:
            panel.show_next_page_loading()
        self._extend_content(self._content_kind(), token, show, self._content_session)

    @work(thread=True, exclusive=True, group="ch_extend")
    def _extend_content(self, kind: str, token: str, show: bool, session: int) -> None:
        page = innertube.ChannelPage([])
        try:
            if kind == "playlist":
                page = playlist_fetch.page_fetcher(self._playlist["id"])(self._playlist["id"], token)
            else:
                page = innertube.fetch_channel_page(self._channel_id() or "", kind, token)
                self._label(page.entries)
        except Exception as exc:
            logger.debug("channel extend: %s", exc)
        self._call_ui(self._apply_extension, session, page, show)

    def _apply_extension(self, session: int, page: innertube.ChannelPage, show: bool) -> None:
        if session != self._content_session:
            return
        panel = self._list()
        entries = self._pager.finish(page.entries, page.token)
        show = show or self._pending_show
        self._pending_show = False
        panel.set_progress(self._pager.note())
        if entries:
            panel.append_pages(entries, show)
        elif show:
            panel.load_page(panel.total_pages, cursor="last")
        self._maybe_prefetch()

    def _known_id(self) -> str | None:
        """The id without a lookup: from the URL or the loaded info. Safe on the UI thread."""
        known = channel_ref.channel_id(self._channel_url)
        if known:
            return known
        try:
            info = self._info_panel().info
        except Exception:
            info = None
        if info and channel_ref.is_channel_id(info.get("channel_id", "")):
            return info["channel_id"]
        return self._resolved_id or None

    def _channel_id(self) -> str | None:
        """The ``UC…`` id: from the URL, the loaded channel info, or one lookup (workers only: it blocks)."""
        known = self._known_id()
        if known:
            return known
        if self._resolved_id is None:
            self._resolved_id = innertube.resolve_channel_id(self._channel_url) or ""
        return self._resolved_id or None

    def _content_kind(self) -> str:
        return "playlist" if self._playlist else self._tab_kind()
