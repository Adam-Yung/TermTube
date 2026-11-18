from __future__ import annotations

import time
import webbrowser

from src import logger
from src.entries import Entry
from src.plat import clipboard_copy

_HINT_REPEAT_S = 2.0


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _is_video(entry: Entry | None) -> bool:
    """True for a row that is a playable video, not a playlist or channel placeholder."""
    return bool(entry) and not entry.get("_is_playlist") and not entry.get("_is_channel")


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
    return "" if not vid or vid.startswith("__") else watch_url(vid)


class ItemActionsMixin:
    """Actions on the highlighted row: play, download, copy, open, and the Enter menu.

    Needs ``_selected_entry()`` (``ListNavMixin``) and ``_sync_player_bar()`` (``AudioBarMixin``).
    Audio keys act on ``app.audio``, the one controller shared by every screen.
    """

    def _hidden_menu_actions(self, entry: Entry) -> set[str]:
        audio = self.app.audio
        hidden: set[str] = set()
        if audio.is_playing:
            hidden |= {"watch", "watch_quality"}
            if not audio.can_enqueue(entry):  # it is the current track or already queued
                hidden.add("enqueue")
        return hidden

    def _menu_labels(self) -> dict[str, str]:
        """Label overrides for the Enter menu: with nothing playing, ``e`` starts playback instead of queueing."""
        if self.app.audio.is_playing:
            return {}
        return {"enqueue": "Play audio, queue more after  [dim](e)[/dim]"}

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
        self._hint("Audio is playing. Stop it with x before watching video.")
        return True

    def action_activate(self) -> None:
        entry = self._selected_entry()
        if entry:
            self._activate_entry(entry)

    def _activate_entry(self, entry: Entry) -> None:
        self._open_action_menu(entry)

    def _open_action_menu(self, entry: Entry) -> None:
        from src.tui.screens.video_action_modal import VideoActionModal

        dispatch = {
            "watch": self.action_watch,
            "watch_quality": self.action_watch_quality,
            "audio": self.action_audio,
            "audio_quality": self.action_audio_quality,
            "enqueue": self.action_audio_enqueue,
            "download": self.action_download,
            "channel": self.action_channel,
            "copy_url": self.action_copy_url,
            "playlist": self.action_playlist,
            "browser": self.action_browser,
        }

        def on_action(key: str | None) -> None:
            if key in dispatch:
                dispatch[key]()

        self.app.push_screen(
            VideoActionModal(entry, hide=self._hidden_menu_actions(entry), labels=self._menu_labels()), on_action
        )

    def _playable_entry(self) -> Entry | None:
        entry = self._selected_entry()
        if entry and not _is_video(entry):
            self._hint("Not a video.", "information")
            return None
        if entry and entry.get("_missing_file"):
            self._hint("The file is missing. Press D to remove this entry.", "information")
            return None
        return entry

    def action_watch(self) -> None:
        entry = self._playable_entry()
        if entry:
            self._watch(entry)

    def action_watch_quality(self) -> None:
        entry = self._playable_entry()
        if entry and not self._video_blocked_by_audio():
            self._pick_quality(audio_only=False, then=lambda fmt: self._watch(entry, fmt))

    def _watch(self, entry: Entry, ytdl_format: str = "") -> None:
        from src.tui.screens.watch_modal import WatchModal

        if self._video_blocked_by_audio():
            return
        logger.info("watch %s", entry.get("id", "?"))
        self.app.push_screen(WatchModal(entry, ytdl_format=ytdl_format))

    def _pick_quality(self, *, audio_only: bool, then) -> None:
        from src.tui.screens.quality_modal import QualityModal

        def on_pick(fmt: str | None) -> None:
            if fmt is not None:
                then(fmt)

        self.app.push_screen(QualityModal(audio_only=audio_only), on_pick)

    def action_audio(self) -> None:
        entry = self._playable_entry()
        if not entry:
            return
        audio = self.app.audio
        if audio.is_playing and entry.get("id") == (audio.entry or {}).get("id"):
            self._hint("Already playing this track.", "information")
            return
        self._play_audio(entry)

    def action_audio_quality(self) -> None:
        entry = self._playable_entry()
        if entry:
            self._pick_quality(audio_only=True, then=lambda fmt: self._play_audio(entry, fmt))

    def _play_audio(self, entry: Entry, ytdl_format: str = "") -> None:
        self.app.audio.play_audio(entry, ytdl_format=ytdl_format)
        self._sync_player_bar()

    def action_audio_enqueue(self) -> None:
        entry = self._playable_entry()
        if entry:
            self.app.audio.enqueue_audio(entry)
            self._sync_player_bar()

    def action_audio_skip(self) -> None:
        audio = self.app.audio
        if not audio.is_playing:
            self._hint("Nothing playing.", "information")
        elif not audio.queue:
            self._hint("Queue is empty.", "information")
        else:
            audio.skip_audio()

    def action_audio_pause(self) -> None:
        if not self.app.audio.is_playing:
            self._hint("Nothing playing.", "information")
            return
        self.app.audio.toggle_audio_pause()

    def action_audio_stop(self) -> None:
        if not self.app.audio.is_playing:
            self._hint("Nothing playing.", "information")
            return
        self.app.audio.stop_audio()

    def action_audio_seek(self, seconds: float) -> None:
        self.app.audio.seek_audio(seconds)

    def action_audio_seek_pct(self, percent: float) -> None:
        self.app.audio.seek_audio_percent(percent)

    def action_download(self) -> None:
        entry = self._playable_entry()
        if not entry:
            return
        if entry.get("is_live") or entry.get("live_status") == "is_live":
            self._hint("Live stream: cannot download.")
            return
        if entry.get("_has_audio"):  # library merges a video with its audio file: both forms exist
            self._hint("Already downloaded as video and audio.", "information")
            return
        from src.tui.screens.download_picker_modal import DownloadPickerModal

        def on_pick(result: tuple[str, str] | None) -> None:
            if result is not None:
                kind, fmt = result
                self._download(entry, audio_only=kind == "audio", fmt=fmt)

        self.app.push_screen(
            DownloadPickerModal(title=entry.get("title", entry.get("id", ""))), on_pick
        )

    def _download(self, entry: Entry, *, audio_only: bool, fmt: str) -> None:
        from src.tui.screens.download_modal import DownloadModal

        title = entry.get("title", entry.get("id", ""))
        kind = "audio" if audio_only else "video"

        def on_done(success: bool | None) -> None:
            if success:
                self.notify(f"✓ Downloaded {kind}: {title[:40]}", timeout=5)
            else:
                self.notify(
                    "✗ Download failed or cancelled", severity="warning", timeout=4
                )

        self.app.push_screen(
            DownloadModal(entry.get("id", ""), entry, audio_only=audio_only, fmt=fmt), on_done
        )

    def action_channel(self) -> None:
        entry = self._selected_entry()
        if entry:
            self._open_channel(entry)

    def _open_channel(self, entry: Entry) -> None:
        from src.tui.screens.channel_screen import ChannelScreen

        url = entry.get("channel_url") or entry.get("uploader_url")
        if not url:
            uid = entry.get("uploader_id") or entry.get("channel_id")
            if uid:
                url = f"https://www.youtube.com/{uid}" if uid.startswith("@") else f"https://www.youtube.com/channel/{uid}"
        if not url:
            self.notify("No channel URL found.", severity="warning")
            return
        name = entry.get("uploader") or entry.get("channel") or "Channel"
        self.app.push_screen(ChannelScreen(channel_url=url, channel_name=name, trail=self._crumbs()))

    def _crumbs(self) -> list[str]:
        """Where this screen sits, for the breadcrumb of a channel page opened from here."""
        return []

    def action_playlist(self) -> None:
        entry = self._playable_entry()
        if not entry:
            return
        from src.tui.screens.playlist_modal import PlaylistModal

        def on_done(_: None) -> None:
            self._detail().refresh_playlists(entry.get("id", ""))

        self.app.push_screen(PlaylistModal(entry), on_done)

    def action_copy_url(self) -> None:
        url = _page_url(self._selected_entry())
        if not url:
            self._hint("No URL available.")
        elif clipboard_copy(url):
            self.notify("URL copied to clipboard")
        else:
            self.notify(f"URL: {url}", timeout=10)

    def action_browser(self) -> None:
        url = _page_url(self._selected_entry())
        if not url:
            self._hint("No URL available.")
            return
        webbrowser.open(url)
        self.notify("Opened in browser")
