from __future__ import annotations

import time
import webbrowser
from collections.abc import Callable
from functools import partial

from src import logger
from src.entries import Entry
from src.local_files import is_local_id
from src.plat import clipboard_copy
from src.progress import is_live
from src.strings import text
from src.tui import keymap
from src.tui.fmt import escape_markup
from src.tui.screens.mixins.playlist_rows import PlaylistRowsMixin
from src.tui.urls import watch_url
from src.tui.widgets.video_list import VideoListPanel

_HINT_REPEAT_S = 2.0
_PLAYABLE_ACTIONS = {"watch", "watch_quality", "audio", "audio_quality", "audio_enqueue"}
_YOUTUBE_ACTIONS = {"download", "channel", "copy_url", "browser", "watch_quality", "audio_quality"}
"""Row actions that need YouTube (a quality is a yt-dlp format): a local file row hides them."""


def _is_video(entry: Entry | None) -> bool:
    """True for a row that is a playable video, not a playlist, channel or folder placeholder."""
    return bool(entry) and not any(entry.get(k) for k in ("_is_playlist", "_is_channel", "_is_folder"))


def _page_url(entry: Entry | None) -> str:
    """The YouTube page of a row: the video, the channel, or the playlist. Empty for local placeholders."""
    if not entry:
        return ""
    if entry.get("_is_channel"):
        return entry.get("channel_url") or entry.get("uploader_url") or ""
    if entry.get("_is_playlist"):
        url = entry.get("url") or ""
        return url if url.startswith("http") else ""
    vid = entry.get("id", "")
    return "" if not vid or vid.startswith("__") or is_local_id(vid) else watch_url(vid)


class ItemActionsMixin(PlaylistRowsMixin):
    """Actions on the highlighted row: play, download, copy, open, and the Enter menu.

    Needs ``_selected_entry()`` (``ListNavMixin``), ``_sync_player_bar()`` (``AudioBarMixin``) and ``_crumbs()``
    (the screen: the breadcrumb a channel page opened from here starts with).
    Audio keys act on ``app.audio``, the one controller shared by every screen.
    """

    def _hidden_menu_actions(self, entry: Entry) -> set[str]:
        """The row actions the Enter menu leaves out: those that would only answer with a hint for this row."""
        audio = self.app.audio
        hidden: set[str] = set(_YOUTUBE_ACTIONS) if is_local_id(entry.get("id")) else set()
        if entry.get("_missing_file"):
            hidden |= _PLAYABLE_ACTIONS | {"download", "playlist"}
        if is_live(entry) or entry.get("_has_audio"):
            hidden.add("download")
        if audio.is_playing:
            hidden |= {"watch", "watch_quality"}
            if not audio.can_enqueue(entry):  # it is the current track or already queued
                hidden.add("audio_enqueue")
        return hidden

    def _tool_actions(self) -> set[str]:
        """The ``keymap.PANEL_TOOLS`` actions that apply on this screen now; a screen with more tools extends it."""
        return {"filter"}

    def panel_hints(self) -> list[tuple[str, str]]:
        """Actions panel entries: Enter and the row actions that apply to the highlighted row, then the tools."""
        entry = self._selected_entry()
        hints: list[tuple[str, str]] = []
        if entry:
            if entry.get("_is_channel"):
                shown = {"copy_url", "browser"}
                hints.append(("⏎", text("item_actions.open_channel")))
            elif entry.get("_is_parent"):
                shown = set()
                hints.append(("⏎", text("item_actions.open_folder")))
            elif entry.get("_is_playlist") or entry.get("_is_folder"):
                folder = bool(entry.get("_is_folder"))
                shown = ({"audio"} if folder else {"copy_url", "browser", "audio"}) | (
                    set() if self.app.audio.is_playing else {"watch"})
                hints.append(("⏎", text("item_actions.open_folder" if folder else "item_actions.open_playlist")))
                hints.append((keymap.key_of("audio_enqueue"), text("item_actions.queue_playlist")))
            else:
                shown = {row.action for row in keymap.ROW_ACTIONS} - self._hidden_menu_actions(entry)
                hints.append(("⏎", text("item_actions.video_actions")))
            hints += [(keymap.key_of(r.action), r.bar) for r in keymap.ROW_ACTIONS if r.bar and r.action in shown]
        return [*hints, *keymap.tool_hints(self._tool_actions())]

    def _refresh_actions(self) -> None:
        """Redraw the Actions panel after the tab, the row or the focus changed."""
        bar = self._detail().action_bar
        if bar.is_mounted:
            bar.render_actions()

    def _menu_labels(self) -> dict[str, str]:
        """Label overrides for the Enter menu: with nothing playing, ``e`` starts playback instead of queueing."""
        if self.app.audio.is_playing:
            return {}
        return {"audio_enqueue": text("item_actions.menu_play_audio")}

    def _hint(self, message: str, severity: str = "warning") -> None:
        """Short notice for a key that cannot act now. The same message is shown at most once per 2 s (held keys)."""
        seen = self.__dict__.setdefault("_hint_times", {})
        now = time.monotonic()
        if now - seen.get(message, -10.0) >= _HINT_REPEAT_S:
            seen[message] = now
            self.notify(message, severity=severity, timeout=3)

    def _video_blocked_by_audio(self) -> bool:
        """True (with a hint) while background audio plays: video and audio together overlap."""
        if not self.app.audio.is_playing:
            return False
        self._hint(text("item_actions.audio_blocks_video"))
        return True

    def on_video_list_panel_activated(self, message: VideoListPanel.Activated) -> None:
        self.action_activate()

    def action_activate(self) -> None:
        entry = self._selected_entry()
        if entry:
            self._activate_entry(entry)

    def _activate_entry(self, entry: Entry) -> None:
        self._open_action_menu(entry)

    def _open_action_menu(self, entry: Entry) -> None:
        from src.tui.screens.video_action_modal import VideoActionModal

        self.app.push_screen(
            VideoActionModal(entry, hide=self._hidden_menu_actions(entry), labels=self._menu_labels()),
            self._run_menu_action,
        )

    def _run_menu_action(self, action: str | None) -> None:
        if action:
            getattr(self, f"action_{action}")()

    def _playable_entry(self) -> Entry | None:
        entry = self._selected_entry()
        if entry and not _is_video(entry):
            self._hint(text("item_actions.not_a_video"), "information")
            return None
        if entry and entry.get("_missing_file"):
            self._hint(text("item_actions.file_missing"), "information")
            return None
        return entry

    def action_watch(self) -> None:
        if self._use_playlist("video"):
            return
        entry = self._playable_entry()
        if entry:
            self._watch(entry)

    def action_watch_quality(self) -> None:
        entry = self._playable_entry()
        if entry and not self._local_refused(entry) and not self._video_blocked_by_audio():
            self._pick_quality(audio_only=False, then=lambda fmt: self._watch(entry, fmt))

    def _watch(self, entry: Entry, ytdl_format: str = "") -> None:
        from src.tui.screens.watch_modal import WatchModal

        if self._video_blocked_by_audio():
            return
        logger.info("watch %s", entry.get("id", "?"))
        self.app.push_screen(WatchModal(entry, ytdl_format=ytdl_format))

    def _pick_quality(self, *, audio_only: bool, then: Callable[[str], None]) -> None:
        from src.tui.screens.quality_modal import QualityModal

        self.app.push_screen(QualityModal(audio_only=audio_only), partial(self._on_quality_picked, then))

    def _on_quality_picked(self, then: Callable[[str], None], fmt: str | None) -> None:
        if fmt is not None:
            then(fmt)

    def action_audio(self) -> None:
        if self._use_playlist("audio"):
            return
        entry = self._playable_entry()
        if not entry:
            return
        audio = self.app.audio
        if audio.is_playing and entry.get("id") == (audio.entry or {}).get("id"):
            self._hint(text("item_actions.already_playing"), "information")
            return
        self._play_audio(entry)

    def action_audio_quality(self) -> None:
        entry = self._playable_entry()
        if entry and not self._local_refused(entry):
            self._pick_quality(audio_only=True, then=lambda fmt: self._play_audio(entry, fmt))

    def _play_audio(self, entry: Entry, ytdl_format: str = "") -> None:
        self.app.audio.play_audio(entry, ytdl_format=ytdl_format)
        self._sync_player_bar()

    def action_audio_enqueue(self) -> None:
        if self._use_playlist("enqueue"):
            return
        entry = self._playable_entry()
        if entry:
            self.app.audio.enqueue_audio(entry)
            self._sync_player_bar()

    def _audio_or_hint(self) -> bool:
        """True while background audio plays; otherwise the key says why it did nothing."""
        if self.app.audio.is_playing:
            return True
        self._hint(text("item_actions.nothing_playing"), "information")
        return False

    def action_audio_skip(self) -> None:
        if not self._audio_or_hint():
            return
        if not self.app.audio.queue:
            self._hint(text("item_actions.queue_empty"), "information")
        else:
            self.app.audio.skip_audio()

    def action_audio_prev(self) -> None:
        if not self._audio_or_hint():
            return
        if not self.app.audio.has_previous:
            self._hint(text("item_actions.no_previous"), "information")
        else:
            self.app.audio.previous_audio()

    def action_audio_queue(self) -> None:
        from src.tui.screens.queue_screen import QueueScreen

        self.app.push_screen(QueueScreen())

    def action_audio_pause(self) -> None:
        if self._audio_or_hint():
            self.app.audio.toggle_audio_pause()

    def action_audio_stop(self) -> None:
        if self._audio_or_hint():
            self.app.audio.stop_audio()

    def action_audio_seek(self, seconds: float) -> None:
        self.app.audio.seek_audio(seconds)

    def action_audio_seek_pct(self, percent: float) -> None:
        self.app.audio.seek_audio_percent(percent)

    def _local_refused(self, entry: Entry | None) -> bool:
        """True (with the reason) for a local file row, which has no YouTube page, channel or download."""
        if entry and is_local_id(entry.get("id")):
            self._hint(text("local_tab.youtube_only"), "information")
            return True
        return False

    def action_download(self) -> None:
        entry = self._playable_entry()
        if not entry or self._local_refused(entry):
            return
        if is_live(entry):
            self._hint(text("item_actions.live_no_download"))
            return
        if entry.get("_has_audio"):  # library merges a video with its audio file: both forms exist
            self._hint(text("item_actions.already_downloaded"), "information")
            return
        from src.tui.screens.download_picker_modal import DownloadPickerModal

        self.app.push_screen(
            DownloadPickerModal(title=entry.get("title", entry.get("id", ""))), partial(self._on_download_picked, entry)
        )

    def _on_download_picked(self, entry: Entry, result: tuple[str, str] | None) -> None:
        if result is not None:
            kind, fmt = result
            self._download(entry, audio_only=kind == "audio", fmt=fmt)

    def _download(self, entry: Entry, *, audio_only: bool, fmt: str) -> None:
        from src.tui.screens.download_modal import DownloadModal

        title = entry.get("title", entry.get("id", ""))
        key = "item_actions.downloaded_audio" if audio_only else "item_actions.downloaded_video"
        self.app.push_screen(
            DownloadModal(entry.get("id", ""), entry, audio_only=audio_only, fmt=fmt),
            partial(self._on_download_done, key, title),
        )

    def _on_download_done(self, key: str, title: str, success: bool | None) -> None:
        if success:
            self.notify(text(key, title=escape_markup(title[:40])), timeout=5)
        else:
            self.notify(text("item_actions.download_failed"), severity="warning", timeout=4)

    def action_channel(self) -> None:
        entry = self._selected_entry()
        if entry and not self._local_refused(entry):
            self._open_channel(entry)

    def _open_channel(self, entry: Entry) -> None:
        from src.tui.screens.channel_screen import ChannelScreen

        url = entry.get("channel_url") or entry.get("uploader_url")
        if not url:
            uid = entry.get("uploader_id") or entry.get("channel_id")
            if uid:
                url = f"https://www.youtube.com/{uid}" if uid.startswith("@") else f"https://www.youtube.com/channel/{uid}"
        if not url:
            self.notify(text("item_actions.no_channel_url"), severity="warning")
            return
        name = entry.get("uploader") or entry.get("channel") or text("item_actions.default_channel_name")
        self.app.push_screen(ChannelScreen(channel_url=url, channel_name=name, trail=self._crumbs()))

    def _open_playlist(self, entry: Entry) -> None:
        """A playlist row from Search or Home: its page, the channel page in playlist mode."""
        from src.tui.screens.channel_screen import ChannelScreen

        if not entry.get("id"):
            self._hint(text("item_actions.not_a_video"), "information")
            return
        self.app.push_screen(ChannelScreen("", "", trail=self._crumbs(), playlist=entry))

    def action_playlist(self) -> None:
        entry = self._playable_entry()
        if not entry:
            return
        from src.tui.screens.playlist_modal import PlaylistModal

        self.app.push_screen(PlaylistModal(entry), partial(self._on_playlists_closed, entry))

    def _on_playlists_closed(self, entry: Entry, _result: None) -> None:
        self._detail().refresh_playlists(entry.get("id", ""))

    def action_copy_url(self) -> None:
        entry = self._selected_entry()
        if self._local_refused(entry):
            return
        url = _page_url(entry)
        if not url:
            self._hint(text("item_actions.no_url"))
        elif clipboard_copy(url):
            self.notify(text("item_actions.url_copied"))
        else:
            self.notify(text("item_actions.url_shown", url=escape_markup(url)), timeout=10)

    def action_browser(self) -> None:
        entry = self._selected_entry()
        if self._local_refused(entry):
            return
        url = _page_url(entry)
        if not url:
            self._hint(text("item_actions.no_url"))
            return
        webbrowser.open(url)
        self.notify(text("item_actions.opened_in_browser"))
