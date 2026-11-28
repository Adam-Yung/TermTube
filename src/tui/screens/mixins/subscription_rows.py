from __future__ import annotations

from textual import work

from src import logger
from src.entries import Entry
from src.tui.thumb_loader import load_thumbnail


class SubscriptionRowsMixin:
    """Fills the detail panel for a channel row: avatar and channel info.

    Needs ``_detail()``, ``_cancel_pending_focus_and_thumb``, ``_worker_start``, ``_worker_end`` and ``app``, and an
    ``_avatar_session`` the screen bumps when the cursor leaves a row.
    """

    def _focus_channel(self, entry: Entry) -> None:
        vid = entry.get("id", "")
        detail = self._detail()
        detail.update_channel_entry(entry)
        self._cancel_pending_focus_and_thumb()
        if vid:
            detail.set_thumbnail_video_id(vid)
            detail.set_thumbnail_loading()
        self._load_channel_avatar(vid, entry.get("thumbnail", ""), entry)

    def _load_channel_avatar(self, vid: str, thumb_url: str, entry: Entry) -> None:
        if not vid:
            return
        if thumb_url:
            self._start_avatar(vid, thumb_url)
        if not entry.get("description") or not thumb_url:
            self._channel_info_worker(vid, entry)

    def _start_avatar(self, vid: str, url: str) -> None:
        self._avatar_session += 1
        self._avatar_worker(vid, url, self._avatar_session)

    @work(thread=True, exclusive=True, group="ch_thumb")
    def _avatar_worker(self, vid: str, url: str, session: int) -> None:
        detail = self._detail()
        cols, rows = detail.thumbnail_cell_size()
        load_thumbnail(
            self.app, detail, vid, url=url, cols=cols, rows=rows,
            is_current=lambda: session == self._avatar_session,
        )

    @work(thread=True, exclusive=True, group="ch_focus")
    def _channel_info_worker(self, vid: str, entry: Entry) -> None:
        import src.ytdlp as ytdlp

        url = entry.get("channel_url") or entry.get("uploader_url")
        if not url:
            return
        self._worker_start()
        try:
            info = ytdlp.fetch_channel_info(url, self.app.config, self.app.cache)
            if info:
                self.app.call_from_thread(self._apply_channel_info, vid, info)
        except Exception as exc:
            logger.debug("channel info %s: %s", vid, exc)
        finally:
            self._worker_end()

    def _apply_channel_info(self, vid: str, info: dict) -> None:
        detail = self._detail()
        if detail.current_id != vid:
            return
        merged = {**(detail.last_entry or {}), **info}
        detail.update_channel_entry(merged)
        thumb_url = merged.get("thumbnail", "")
        if thumb_url:
            self._start_avatar(vid, thumb_url)
