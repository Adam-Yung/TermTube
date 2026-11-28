from __future__ import annotations

from collections.abc import Callable
from functools import partial

from textual import work

from src import local_files, logger, playlist_fetch
from src.entries import Entry, VideoEntry
from src.errors import classify
from src.strings import text

PlaylistLoader = Callable[[], tuple[list[VideoEntry], str]]

_STEPS = {"ended": 1, "next": 1, "failed": 1, "prev": -1}
_MAX_FAILURES = 3  # offline, every item fails: do not walk 200 videos asking YouTube for each


class PlaylistRowsMixin:
    """``v`` ``a`` ``e`` on a playlist or folder row: play it as video or audio, or queue it, without opening it.

    Needs ``_selected_entry``, ``_hint``, ``_video_blocked_by_audio``, ``_sync_player_bar`` and ``app`` from the screen.
    """

    def _playlist_source(self) -> PlaylistLoader | None:
        """How to load the playlist under the cursor, or None when the cursor is not on one."""
        row = self._selected_entry()
        if row and row.get("_is_folder"):
            return partial(local_files.folder_tracks, row["_local_path"])
        if not (row and row.get("_is_playlist") and row.get("id")):
            return None
        config, cache = self.app.config, self.app.cache
        return lambda: playlist_fetch.fetch_videos(row, config, cache)

    def _use_playlist(self, mode: str) -> bool:
        """Start ``mode`` (``video``, ``audio``, ``enqueue``) on a playlist row. False when there is none."""
        row = self._selected_entry()
        if row and row.get("_is_parent"):
            self._hint(text("local_tab.parent_not_played"), "information")
            return True
        load = self._playlist_source()
        if load is None:
            return False
        if mode == "video" and self._video_blocked_by_audio():
            return True
        ticket = self.app.audio.claim()
        self.notify(text("playlist_rows.loading"), timeout=3)
        self._load_playlist_worker(load, mode, ticket)
        return True

    @work(thread=True, exclusive=True, group="playlist_row")
    def _load_playlist_worker(self, load: PlaylistLoader, mode: str, ticket: int) -> None:
        try:
            videos, reason = load()
        except Exception as exc:
            logger.debug("playlist row: %s", exc)
            self.app.call_from_thread(self._hint, classify(exc).message, "error")
            return
        self.app.call_from_thread(self._start_playlist, videos, reason, mode, ticket)

    def _start_playlist(self, videos: list[VideoEntry], reason: str, mode: str, ticket: int) -> None:
        audio = self.app.audio
        if ticket != audio.intent:  # something else was asked for while this one loaded
            return
        if not videos:
            self._hint(reason or text("channel_playlist.no_videos"), "information")
            return
        if mode == "video":
            if self.app.screen is self and not self._video_blocked_by_audio():
                self._watch_run(videos, 0)
            return
        if mode == "enqueue":
            if not audio.enqueue_many(videos):
                self._hint(text("playlist_tools.all_queued"), "information")
        else:
            audio.play_many(videos)
            key = "channel_playlist.play_one" if len(videos) == 1 else "channel_playlist.play_many"
            self.notify(text(key, count=len(videos)), timeout=3)
        if self in self.app.screen_stack:
            self._sync_player_bar()

    def _watch_run(self, videos: list[Entry], index: int, failures: int = 0) -> None:
        """Play ``videos[index]`` in the video player, then its neighbour, until stopped or past the end."""
        from src.tui.screens.watch_modal import WatchModal

        entry: Entry = videos[index]
        logger.info("watch %s (%d of %d)", entry.get("id", "?"), index + 1, len(videos))
        self.app.push_screen(
            WatchModal(entry, position=(index + 1, len(videos))),
            partial(self._on_run_item_done, videos, index, failures),
        )

    def _on_run_item_done(self, videos: list[Entry], index: int, failures: int, result: str | None) -> None:
        step = _STEPS.get(result or "")
        failed = failures + 1 if result == "failed" else 0
        if step is None or failed >= _MAX_FAILURES:
            return
        following = max(0, index + step)
        if following >= len(videos):
            self.notify(text("playlist_rows.finished"), timeout=4)
            return
        self._watch_run(videos, following, failed)
