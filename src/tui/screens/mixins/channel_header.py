from __future__ import annotations

import re

from textual import work

from src import logger
from src.strings import text
from src.tui.fmt import fmt_breadcrumb
from src.tui.screens.channel_tabs import TAB_LABELS
from src.tui.thumb_loader import load_thumbnail
from src.tui.widgets.channel_info_panel import ChannelInfoPanel, playlist_panel_info

_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def _avatar_id(info: dict) -> str:
    raw = info.get("channel_id") or info.get("uploader_id")
    if not raw:
        raw = _UNSAFE_ID_CHARS.sub("_", info.get("channel_url", "")[:60])
    return "ch_" + raw[:50]


class ChannelHeaderMixin:
    """The channel page's left column and breadcrumb: channel or playlist info and its avatar.

    Needs ``_channel_url``, ``_channel_name``, ``_trail``, ``_playlist``, ``_solo``, ``_owner``, ``_tab_kind``,
    ``_show_tabs``, ``_list``, ``_call_ui``, ``query_one`` and ``app`` from the screen.
    """

    def _info_panel(self) -> ChannelInfoPanel:
        return self.query_one("#ch-info-panel", ChannelInfoPanel)

    def _crumbs(self) -> list[str]:
        return [*self._trail, self._display_name()]

    def _display_name(self) -> str:
        info = self._info_panel().info or {}
        return info.get("channel") or self._channel_name or text("channel_screen.channel_fallback")

    def _show_breadcrumb(self) -> None:
        if self._solo:
            name = self._display_name() if self._info_panel().info else self._playlist_title()
            crumb = text("channel_screen.playlist_crumb", name=name)
            self._list().set_breadcrumb(text("channel_screen.breadcrumb", trail=fmt_breadcrumb([*self._trail, crumb])))
            return
        parts = [*self._crumbs(), text(TAB_LABELS[self._tab_kind()])]
        if self._playlist:
            fallback = text("channel_screen.playlist_fallback")
            parts.append(self._playlist.get("_playlist_name") or self._playlist.get("title", fallback))
        self._list().set_breadcrumb(text("channel_screen.breadcrumb", trail=fmt_breadcrumb(parts)))

    @work(thread=True, exclusive=True, group="ch_info")
    def _load_channel_info(self) -> None:
        import src.ytdlp as ytdlp

        try:
            info = ytdlp.fetch_channel_info(self._channel_url, self.app.config, self.app.cache)
        except Exception as exc:
            logger.debug("channel info: %s", exc)
            info = None
        if info:
            self._call_ui(self._apply_info, info)
        else:
            self._call_ui(self._show_info_error)

    def _playlist_title(self) -> str:
        row = self._playlist or {}
        return row.get("_playlist_name") or row.get("title") or text("channel_screen.playlist_untitled")

    def _apply_playlist_info(self, info: dict | None) -> None:
        """The left column of a playlist page: the header from the first page, or just the row's title without one."""
        info = info or {}
        self._owner = (info.get("owner", ""), info.get("owner_id", ""))
        header = {"playlist_id": self._playlist["id"], **info}
        self._apply_info(playlist_panel_info(header, self._playlist_title()))

    def _show_info_error(self) -> None:
        self._info_panel().show_error()

    def _apply_info(self, info: dict) -> None:
        panel = self._info_panel()
        panel.update_info(info)
        self._show_breadcrumb()
        known = tuple(kind for kind in TAB_LABELS if kind in info.get("tabs", ()))
        if "videos" in known and not self._solo:
            self._show_tabs(known)
        url = info.get("thumbnail", "")
        if not url:
            panel.set_thumbnail_placeholder()
            return
        avatar_id = _avatar_id(info)
        panel.set_avatar_id(avatar_id)
        panel.set_thumbnail_loading()
        self._info_avatar_session += 1
        self._avatar_worker(avatar_id, url, self._info_avatar_session)

    @work(thread=True, exclusive=True, group="ch_thumb")
    def _avatar_worker(self, avatar_id: str, url: str, session: int) -> None:
        load_thumbnail(
            self.app, self._info_panel(), avatar_id, url=url,
            is_current=lambda: session == self._info_avatar_session,
        )
