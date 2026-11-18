from __future__ import annotations

from textual import work

from src import innertube, logger, playlist
from src.channel_pager import MAX_ENTRIES
from src.entries import Entry, PlaylistEntry, VideoEntry

_BULK_NOUN = {"play": "Playing", "enqueue": "Queued", "save": "Saved"}


class ChannelPlaylistMixin:
    """A channel's playlist opened inside the channel page: its videos as a list, plus play all, enqueue all and save.

    Needs ``_list``, ``_pager``, ``_content_session``, ``_start_content_load``, ``_hint``, ``_sync_player_bar`` and
    ``app`` from the screen. ``_playlist`` is the open playlist row, or None on the ordinary tabs.
    """

    _playlist: PlaylistEntry | None = None

    def _activate_entry(self, entry: Entry) -> None:
        if entry.get("_is_playlist") and entry.get("id"):
            self._playlist = entry
            self._start_content_load()
        else:
            super()._activate_entry(entry)

    def _leave_playlist(self) -> bool:
        """Back to the Playlists tab list. False when no playlist was open."""
        if self._playlist is None:
            return False
        self._playlist = None
        self._start_content_load()
        return True

    def _fetch_playlist_videos(self) -> innertube.ChannelPage:
        """InnerTube browse of the playlist; yt-dlp when it comes back empty."""
        import src.ytdlp as ytdlp

        page = innertube.fetch_playlist_page(self._playlist["id"])
        if page.entries:
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
            self._hint("Open a playlist first (Enter on a playlist row).", "information")
            return
        panel = self._list()
        if panel.is_loading or self._pager.fetching:
            self._hint("Still loading the playlist.", "information")
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
                page = innertube.fetch_playlist_page(source["id"], token)
                entries.extend(page.entries)
                token = page.token
                if not token:
                    break
        except Exception as exc:
            logger.debug("gather playlist: %s", exc)
        self.app.call_from_thread(self._run_bulk, action, source, entries[:MAX_ENTRIES], session)

    def _run_bulk(self, action: str, source: PlaylistEntry, entries: list[Entry], session: int) -> None:
        if session != self._content_session:
            return
        videos = [e for e in entries if e.get("id") and not e.get("_is_playlist") and not e.get("_is_channel")]
        if not videos:
            self._hint("No videos to use.", "information")
            return
        audio = self.app.audio
        if action == "play":
            count = audio.play_all(videos)
        elif action == "enqueue":
            count = audio.enqueue_many(videos)
        else:
            count = self._save_local(source, videos)
        if action != "enqueue":
            self.notify(f"{_BULK_NOUN[action]} {count} video{'s' if count != 1 else ''}", timeout=3)
        self._sync_player_bar()

    def _save_local(self, source: PlaylistEntry, videos: list[VideoEntry]) -> int:
        """Add the videos to the local playlist named like the channel playlist, keeping their rows in the cache."""
        for video in videos:
            self.app.cache.put_video(video)
        name = source.get("_playlist_name") or source.get("title") or source["id"]
        playlist.add_videos(name, [v["id"] for v in videos])
        return len(videos)
