"""One lazy yt-dlp listing of an account feed, advanced in steps instead of re-read from the top."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator

import yt_dlp

from src import logger, ytdlp
from src.cookies import invalidate
from src.errors import SignInRequired, SourceError, classify

MAX_FEED_ENTRIES = 1000
"""A cursor stops after this many rows of the feed, so a feed that never ends cannot grow without bound."""


class FeedCursor:
    """Keeps one flat, lazy extraction open per loaded view and hands out the next entries on request.

    ``take`` is called from worker threads, one at a time (a lock serialises them). ``close`` may be called
    from any thread: it cancels at once, and when a ``take`` is mid-flight that ``take`` closes the
    extractor as it returns, so the generator is never touched from two threads. A failed ``take`` drops the
    extraction (the generator is dead) and the next one reopens the feed from the top, skipping ``skip_ids``.
    """

    def __init__(self, url: str, config, cache, *, auth: bool = False, playlists: bool = False) -> None:
        self.url = url
        self._config, self._cache, self._auth, self._playlists = config, cache, auth, playlists
        self.ids: list[str] = []
        self.exhausted = False
        self._consumed = 0
        self._ydl: yt_dlp.YoutubeDL | None = None
        self._rows: Iterator[dict] | None = None
        self._lock = threading.Lock()
        self._cancel = ytdlp.new_cancel_event()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed or self._cancel.is_set()

    def close(self) -> None:
        self._closed = True
        self._cancel.set()
        ytdlp.release_cancel_event(self._cancel)
        if self._lock.acquire(blocking=False):
            try:
                self._drop()
            finally:
                self._lock.release()

    def _drop(self) -> None:
        ydl, self._ydl, self._rows = self._ydl, None, None
        if ydl is not None:
            try:
                ydl.__exit__(None, None, None)
            except Exception as exc:
                logger.debug("feed cursor close: %s", exc)

    def _open(self) -> None:
        opts = ytdlp._flat_opts(MAX_FEED_ENTRIES)
        ydl = ytdlp._make_ydl(opts, self._config, auth=self._auth)
        ydl.__enter__()
        self._ydl = ydl
        info = ydl.extract_info(self.url, download=False)
        self._rows = iter((info or {}).get("entries") or [])
        self._consumed = 0

    def take(
        self,
        count: int,
        skip_ids: set[str],
        *,
        on_first_batch: Callable[[list[dict]], None] | None = None,
        first_batch_size: int = 15,
    ) -> list[dict]:
        """The next ``count`` playable entries not in ``skip_ids`` (fewer when the feed ends or is closed).

        Raises a typed ``SourceError`` when the extraction fails before it yielded anything.
        """
        with self._lock:
            try:
                return self._take(count, skip_ids, on_first_batch, first_batch_size)
            finally:
                if self._closed:
                    self._drop()

    def _take(self, count, skip_ids, on_first_batch, first_batch_size) -> list[dict]:
        if self.closed or self.exhausted:
            return []
        results: list[dict] = []
        failure: SourceError | None = None
        for attempt in range(ytdlp._MAX_RETRIES + 1):
            failure = None
            try:
                if self._rows is None:
                    self._open()
                for entry in self._rows:
                    if self.closed:
                        break
                    self._consumed += 1
                    row = ytdlp.playlist_row(entry) if self._playlists else None
                    if row is not None:
                        entry = row
                    elif ytdlp._is_playable_video(entry):
                        ytdlp._normalise_entry(entry)
                    else:
                        continue
                    vid = entry["id"]
                    if vid in skip_ids:
                        continue
                    self._cache.put_video(entry)
                    self.ids.append(vid)
                    results.append(entry)
                    if on_first_batch and len(results) == first_batch_size:
                        on_first_batch(list(results))
                        on_first_batch = None
                    if len(results) >= count or self.closed:
                        break
                else:
                    self.exhausted = True
                if self._consumed >= MAX_FEED_ENTRIES:
                    self.exhausted = True
            except yt_dlp.utils.DownloadError as exc:
                logger.debug("feed cursor %s error: %s", self.url, exc)
                failure = classify(exc)
                if self._auth and isinstance(failure, SignInRequired):
                    invalidate()
                self._drop()
            if results or self.closed or attempt >= ytdlp._MAX_RETRIES or self._consumed:
                break
            self._drop()
            self.exhausted = False
            time.sleep(ytdlp._RETRY_DELAY_S)
        if failure and not results:
            raise failure
        return results
