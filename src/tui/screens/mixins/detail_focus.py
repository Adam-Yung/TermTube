from __future__ import annotations

from textual import work
from textual.timer import Timer

from src import logger
from src.tui.thumb_loader import load_thumbnail
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel
from src.ui.thumbnail import _thumb_path

FOCUS_DWELL_S = 0.10
THUMB_DWELL_S = 0.15
RERENDER_DEBOUNCE_S = 0.3


class DetailFocusMixin:
    """Fills the detail panel for the row under the cursor.

    A cursor move only paints the cheap fields. The metadata fetch and the thumbnail
    start after a short dwell, so holding ``j`` does not fire a request per row. Each
    worker carries a session number; ``_cancel_pending_focus_and_thumb`` bumps them all,
    and a worker whose number is stale drops its result.

    The screen sets ``_LIST_ID`` and ``_DETAIL_ID``, and calls ``_init_detail_focus``
    from ``__init__``.
    """

    _LIST_ID: str
    _DETAIL_ID: str

    def _init_detail_focus(self) -> None:
        self._focus_dwell_timer: Timer | None = None
        self._thumb_dwell_timer: Timer | None = None
        self._focus_session = 0
        self._thumb_session = 0

    def _detail(self) -> DetailPanel:
        return self.query_one(self._DETAIL_ID, DetailPanel)

    def _worker_start(self) -> None:
        """Hook: a background worker began."""

    def _worker_end(self) -> None:
        """Hook: a background worker finished."""

    def _focus_video(self, entry: dict) -> None:
        vid = entry.get("id", "")
        detail = self._detail()
        detail.update_basic(entry)
        self._cancel_pending_focus_and_thumb()
        if not vid:
            return
        detail.set_thumbnail_video_id(vid)
        is_video = not vid.startswith("__")
        if not is_video or not _thumb_path(vid).exists():
            detail.set_thumbnail_loading()
        if is_video:
            self._thumb_dwell_timer = self.set_timer(
                THUMB_DWELL_S, lambda: self._kick_thumb(vid, entry)
            )
            self._focus_dwell_timer = self.set_timer(
                FOCUS_DWELL_S, lambda: self._kick_focus(vid, entry)
            )

    def _cancel_pending_focus_and_thumb(self) -> None:
        for timer in (self._focus_dwell_timer, self._thumb_dwell_timer):
            if timer is not None:
                timer.stop()
        self._focus_dwell_timer = None
        self._thumb_dwell_timer = None
        self._focus_session += 1
        self._thumb_session += 1

    def _kick_thumb(self, vid: str, entry: dict) -> None:
        self._thumb_dwell_timer = None
        if self._detail().current_id != vid:
            return
        self._thumb_session += 1
        self._thumb_worker(vid, entry, self._thumb_session)

    def _kick_focus(self, vid: str, entry: dict) -> None:
        self._focus_dwell_timer = None
        if self._detail().current_id != vid or entry.get("description"):
            return
        self._focus_session += 1
        self._detail_worker(vid, entry, self._focus_session)

    def on_detail_panel_rerender_requested(self, message: DetailPanel.RerenderRequested) -> None:
        """Re-render the thumbnail after a resize, debounced so a drag does not render per frame."""
        entry = message.entry
        vid = entry.get("id", "")
        if not vid or vid.startswith("__"):
            return
        if self._thumb_dwell_timer:
            self._thumb_dwell_timer.stop()
        self._thumb_dwell_timer = self.set_timer(
            RERENDER_DEBOUNCE_S, lambda: self._kick_thumb(vid, entry)
        )

    @work(thread=True, exclusive=True, group="focus")
    def _detail_worker(self, vid: str, entry: dict, session: int) -> None:
        from src import innertube

        self._worker_start()
        self._prefetch_stream_worker(vid)
        try:
            meta = innertube.fetch_video_details(vid)
            if meta is None or session != self._focus_session:
                return
            merged = {**entry, **{k: v for k, v in meta.items() if v}}
            self.app.cache.put_video(merged)
            panel = self.query_one(self._LIST_ID, VideoListPanel)
            self.app.call_from_thread(panel.update_entry_by_id, vid, merged)
            self.app.call_from_thread(self._detail().refresh_metadata, merged)
        except Exception as exc:
            logger.debug("detail worker %s: %s", vid, exc)
        finally:
            self._worker_end()

    @work(thread=True, exclusive=True, group="stream_prefetch")
    def _prefetch_stream_worker(self, vid: str) -> None:
        import src.ytdlp as ytdlp

        config = self.app.config
        try:
            ytdlp.prefetch_stream_url(vid, config)
            if config.get("prefetch_video", False):
                ytdlp.prefetch_stream_url(vid, config, format_spec="bv+ba/b")
        except Exception as exc:
            logger.debug("stream prefetch %s: %s", vid, exc)

    @work(thread=True, exclusive=True, group="thumb")
    def _thumb_worker(self, vid: str, entry: dict, session: int) -> None:
        detail = self._detail()
        cols, rows = detail.thumbnail_cell_size()
        load_thumbnail(
            self.app, detail, vid, entry=entry, cols=cols, rows=rows,
            is_current=lambda: session == self._thumb_session,
        )
