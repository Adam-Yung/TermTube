from __future__ import annotations

import threading

from textual import work

from src import logger
from src.entries import Entry
from src.tui.fmt import fmt_day_group
from src.tui.widgets.video_list import PAGE_SIZE, VideoListPanel

BATCH_FETCH_COUNT = 80
FIRST_BATCH_COUNT = 15
SEARCH_FETCH_COUNT = 50

FEED_TABS = ("home",)
PAGED_TABS = ("home", "search")
CHANNEL_TABS = ("subscriptions",)

_EXTRACTION_ERRORS = ("unable to extract", "unsupported", "sign in", "http error", "unavailable")


def _day_label(entry: Entry) -> str:
    return fmt_day_group(entry.get("watched_at"))


def _pages_for(count: int) -> int:
    return -(-count // PAGE_SIZE)


class FeedLoaderMixin:
    """Loads each tab's entries into the ``VideoListPanel`` and keeps paging ahead of the user.

    Needs ``_current_tab``, ``_search_query``, ``_feed_session``, ``_log``, ``_worker_start`` and
    ``_worker_end`` from the screen, plus ``_show_empty_feed_modal`` and ``_prompt_ytdlp_update``.
    Tab loads run in the exclusive ``feed_loader`` group and paging in ``feed_extend``, so neither cancels
    the other; ``_feed_session`` makes a paging result from before a view change a no-op.
    """

    def _load_view(self, view: str) -> None:
        self._log(f"[dim]Loading {view}…[/dim]")
        self._list().clear_and_set_loading()
        detail = self._detail()
        detail.clear()
        if view not in CHANNEL_TABS:
            detail.set_video_mode()
        self._start_view(view)

    def _start_view(self, view: str) -> None:
        self._feed_session += 1
        self._stream_view(view)

    @work(thread=True, exclusive=True, group="feed_loader")
    def _stream_view(self, view: str) -> None:
        panel = self._list()
        self._worker_start()
        try:
            if view in FEED_TABS:
                self._load_feed(view, panel)
            elif view in CHANNEL_TABS:
                self._load_subscriptions(panel)
            elif view == "search":
                self._load_search(panel)
            elif view == "history":
                from src import history

                self.app.call_from_thread(
                    lambda: panel.set_view_options(group_by=_day_label, show_count=True)
                )
                self._load_simple_list(panel, history.all_entries())
            elif view == "library":
                from src import library

                config = self.app.config
                self._load_simple_list(
                    panel, list(library.all_entries(config.video_dir, config.audio_dir))
                )
            elif view == "playlists":
                self._load_playlist_index(panel)
            elif view.startswith("playlist:"):
                self._load_playlist_videos(view.removeprefix("playlist:"), panel)
        except Exception as exc:
            msg = str(exc)
            if view in FEED_TABS and any(p in msg.lower() for p in _EXTRACTION_ERRORS):
                self.app.call_from_thread(self._prompt_ytdlp_update, view, msg)
            else:
                self.app.call_from_thread(panel.set_error_message, f"⚠ {msg}")
            self.app.call_from_thread(self._log, f"[red]Error in {view}: {msg}[/red]")
        finally:
            self._worker_end()

    def _show_pages(self, panel: VideoListPanel, entries: list[Entry], *, evict: bool = True) -> None:
        call = self.app.call_from_thread
        call(lambda: panel.add_entries(1, entries, evict=evict))
        call(panel.load_page, 1)
        call(panel.finish_loading)

    def _load_feed(self, feed_key: str, panel: VideoListPanel) -> None:
        """Show the stash instantly, then either serve the disk cache or fetch from yt-dlp.

        The stash is page 1 of the last session. Fresh entries start at page 2 so the
        first screen never changes under the cursor.
        """
        import src.ytdlp as ytdlp

        cache = self.app.cache
        call = self.app.call_from_thread

        def visible(entries: list[Entry]) -> list[Entry]:
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
            pages_used = _pages_for(len(batch))
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
        self.app.call_from_thread(panel.add_entries, 2, entries)
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
            if len(entries) < PAGE_SIZE:
                have = {e.get("id") for e in entries}
                visited = [e for e in panel.visited_entries() if e.get("id") not in have]
                entries += visited[-(PAGE_SIZE - len(entries)):]
            stash = entries[:PAGE_SIZE]
            if stash:
                self.app.cache.put_home_stash(stash)
                logger.debug("stash: saved %d entries", len(stash))
        except Exception as exc:
            logger.debug("stash save: %s", exc)

    def _load_subscriptions(self, panel: VideoListPanel) -> None:
        import src.ytdlp as ytdlp

        entries = ytdlp.fetch_subscribed_channels(self.app.config, self.app.cache)
        if not entries:
            self.app.call_from_thread(self._show_empty_feed_modal, "subscriptions")
            return
        self.app.call_from_thread(self._detail().set_channel_mode)
        self._show_pages(panel, entries)

    def _load_search(self, panel: VideoListPanel) -> None:
        import src.ytdlp as ytdlp

        if not self._search_query:
            self.app.call_from_thread(panel.set_empty_message, "Press / to search")
            return
        call = self.app.call_from_thread
        shown: list[Entry] = []

        def on_first_batch(entries: list[Entry]) -> None:
            shown.extend(entries)
            call(panel.add_entries, 1, entries)
            call(panel.load_page, 1)
            call(panel.finish_loading)

        entries = ytdlp.fetch_search_batch(
            self._search_query, self.app.config, self.app.cache,
            count=SEARCH_FETCH_COUNT, on_first_batch=on_first_batch,
        )
        if not shown:
            self._show_pages(panel, entries)
            return
        shown_ids = {e.get("id") for e in shown}
        rest = [e for e in entries if e.get("id") not in shown_ids]
        if rest:
            call(panel.add_entries, 1 + _pages_for(len(shown)), rest)

    def _load_simple_list(self, panel: VideoListPanel, entries: list[Entry]) -> None:
        if not entries:
            self.app.call_from_thread(panel.set_empty_message, "No items")
            return
        self._show_pages(panel, entries, evict=False)

    def _load_playlist_index(self, panel: VideoListPanel) -> None:
        from src import playlist

        names = playlist.list_names()
        if not names:
            self.app.call_from_thread(panel.set_empty_message, "No playlists. Select a video and press p.")
            return
        entries = []
        for name in names:
            count = len(playlist.get_playlist(name))
            entries.append({
                "id": f"__playlist__{name}",
                "title": f"🎵  {name}",
                "uploader": f"{count} video{'s' if count != 1 else ''}",
                "duration": None,
                "view_count": None,
                "_is_playlist": True,
                "_playlist_name": name,
            })
        self._show_pages(panel, entries, evict=False)

    def _load_playlist_videos(self, name: str, panel: VideoListPanel) -> None:
        from src import playlist

        ids = playlist.get_playlist(name)
        if not ids:
            self.app.call_from_thread(panel.set_empty_message, f'Playlist "{name}" is empty.')
            return
        cache = self.app.cache
        entries = [
            cache.get_video_raw(vid) or {"id": vid, "title": vid, "uploader": ""} for vid in ids
        ]
        self._show_pages(panel, entries, evict=False)

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
        if tab in FEED_TABS:
            entries = ytdlp.fetch_page_batch(
                ytdlp.FEED_URLS[tab], config, cache,
                skip_ids=skip, count=BATCH_FETCH_COUNT, feed_key=None, auth=True,
            )
            if tab == "home":
                entries = [e for e in entries if not cache.is_suppressed(e.get("id", ""))]
            return entries
        if tab == "search" and self._search_query:
            return ytdlp.fetch_search_batch(
                self._search_query, config, cache, skip_ids=skip, count=SEARCH_FETCH_COUNT
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
