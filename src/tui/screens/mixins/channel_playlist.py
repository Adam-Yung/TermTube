from __future__ import annotations

from textual import work

from src import innertube, logger, playlist
from src.channel_pager import MAX_ENTRIES
from src.entries import Entry, PlaylistEntry, VideoEntry
from src.errors import classify
from src.strings import text


class ChannelPlaylistMixin:
    """A channel's playlist opened inside the channel page: its videos as a list, plus play all, enqueue all and save.

    Needs ``_list``, ``_pager``, ``_content_session``, ``_start_content_load``, ``_hint``, ``_sync_player_bar`` and
    ``app`` from the screen. ``_playlist`` is the open playlist row, or None on the ordinary tabs.
    """

    _playlist: PlaylistEntry | None = None
    _solo = False  # the page IS the playlist (opened from Search or Home): there is no Playlists tab to return to

    def _activate_entry(self, entry: Entry) -> None:
        if entry.get("_is_playlist") and entry.get("id"):
            self._playlist = entry
            self._start_content_load()
        else:
            super()._activate_entry(entry)

    def _leave_playlist(self) -> bool:
        """Back to the Playlists tab list. False when no playlist was open."""
        if self._playlist is None or self._solo:
            return False
        self._playlist = None
        self._start_content_load()
        return True

    @staticmethod
    def _page_fetcher(playlist_id: str):
        """A Mix (``RD…``) is read through ``next``; every other playlist through ``browse``."""
        return innertube.fetch_mix_page if playlist_id.startswith("RD") else innertube.fetch_playlist_page

    def _fetch_playlist_videos(self) -> innertube.ChannelPage:
        """InnerTube browse of the playlist; yt-dlp when it comes back empty without a reason."""
        import src.ytdlp as ytdlp

        playlist_id = self._playlist["id"]
        page = self._page_fetcher(playlist_id)(playlist_id)
        # With a reason from YouTube, or for a Mix (yt-dlp has no Mix reader), a second source would add nothing.
        if page.entries or (page.info or {}).get("unavailable") or playlist_id.startswith("RD"):
            return page
        logger.debug("InnerTube playlist empty; falling back to yt-dlp")
        url = self._playlist.get("url") or f"https://www.youtube.com/playlist?list={self._playlist['id']}"
        return innertube.ChannelPage(ytdlp.fetch_page_batch(url, self.app.config, self.app.cache, count=MAX_ENTRIES))

    def action_play_all(self) -> None:
        self._bulk("play")

    def action_enqueue_all(self) -> None:
        self._bulk("enqueue")

    def action_save_list(self) -> None:
        self._bulk("save")

    def _bulk(self, action: str) -> None:
        if self._playlist is None:
            self._hint(text("channel_playlist.open_playlist_first"), "information")
            return
        panel = self._list()
        if panel.is_loading or self._pager.fetching:
            self._hint(text("channel_playlist.still_loading"), "information")
        elif self._pager.token:
            self._gather_playlist(action, self._playlist, self._content_session)
        else:
            self._run_bulk(action, self._playlist, panel.visited_entries(), self._content_session)

    @work(thread=True, exclusive=True, group="ch_gather")
    def _gather_playlist(self, action: str, source: PlaylistEntry, session: int) -> None:
        """The whole playlist (up to the cap) when the list on screen holds only the first pages."""
        entries: list[Entry] = []
        token = ""
        try:
            while len(entries) < MAX_ENTRIES:
                page = self._page_fetcher(source["id"])(source["id"], token)
                entries.extend(page.entries)
                token = page.token
                if not token:
                    break
        except Exception as exc:
            logger.debug("gather playlist: %s", exc)
            self.app.call_from_thread(self._hint, classify(exc).message, "error")
            return
        self.app.call_from_thread(self._run_bulk, action, source, entries[:MAX_ENTRIES], session)

    def _run_bulk(self, action: str, source: PlaylistEntry, entries: list[Entry], session: int) -> None:
        if session != self._content_session:
            return
        videos = [e for e in entries if e.get("id") and not e.get("_is_playlist") and not e.get("_is_channel")]
        if not videos:
            self._hint(text("channel_playlist.no_videos"), "information")
            return
        audio = self.app.audio
        if action == "play":
            videos = list({v["id"]: v for v in videos}.values())
            audio.play_many(videos)
            count = len(videos)
        elif action == "enqueue":
            count = audio.enqueue_many(videos)
        else:
            count = self._save_local(source, videos)
        if action != "enqueue":
            key = f"channel_playlist.{action}_{'one' if count == 1 else 'many'}"
            self.notify(text(key, count=count), timeout=3)
        self._sync_player_bar()

    def _save_local(self, source: PlaylistEntry, videos: list[VideoEntry]) -> int:
        """Add the videos to the local playlist named like the channel playlist, keeping their rows in the cache."""
        for video in videos:
            self.app.cache.put_video(video)
        name = source.get("_playlist_name") or source.get("title") or source["id"]
        existing = playlist.find_by_name(name)
        if existing is None:
            created = playlist.create(name, videos)
            return len(created["items"]) if created else 0
        return playlist.add_items(existing["id"], videos)
