from __future__ import annotations

import webbrowser

from src import logger
from src.plat import clipboard_copy


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _is_video(entry: dict | None) -> bool:
    """True for a row that is a playable video, not a playlist or channel placeholder."""
    return bool(entry) and not entry.get("_is_playlist") and not entry.get("_is_channel")


class ItemActionsMixin:
    """Actions on the highlighted row: play, download, copy, open, and the Enter menu.

    Needs ``_selected_entry()`` (``ListNavMixin``). Audio goes through ``_audio_host()``:
    the screen that owns the mpv process, which is not always the screen showing the list.
    """

    def _audio_host(self):
        """The object with the ``AudioPlayerMixin`` interface."""
        raise NotImplementedError

    def _sync_player_bar(self) -> None:
        """Hook: show the host's current track in this screen's own action bar."""

    def _hidden_menu_actions(self, entry: dict) -> set[str]:
        return set() if self._audio_host().can_enqueue(entry) else {"enqueue"}

    def action_activate(self) -> None:
        entry = self._selected_entry()
        if entry:
            self._activate_entry(entry)

    def _activate_entry(self, entry: dict) -> None:
        self._open_action_menu(entry)

    def _open_action_menu(self, entry: dict) -> None:
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
            VideoActionModal(entry, hide=self._hidden_menu_actions(entry)), on_action
        )

    def _playable_entry(self) -> dict | None:
        entry = self._selected_entry()
        return entry if _is_video(entry) else None

    def action_watch(self) -> None:
        entry = self._playable_entry()
        if entry:
            self._watch(entry)

    def action_watch_quality(self) -> None:
        entry = self._playable_entry()
        if entry:
            self._pick_quality(audio_only=False, then=lambda fmt: self._watch(entry, fmt))

    def _watch(self, entry: dict, ytdl_format: str = "") -> None:
        from src.tui.screens.watch_modal import WatchModal

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
        if entry:
            self._play_audio(entry)

    def action_audio_quality(self) -> None:
        entry = self._playable_entry()
        if entry:
            self._pick_quality(audio_only=True, then=lambda fmt: self._play_audio(entry, fmt))

    def _play_audio(self, entry: dict, ytdl_format: str = "") -> None:
        self._audio_host().play_audio(entry, ytdl_format=ytdl_format)
        self._sync_player_bar()

    def action_audio_enqueue(self) -> None:
        entry = self._playable_entry()
        if entry:
            self._audio_host().enqueue_audio(entry)
            self._sync_player_bar()

    def action_audio_skip(self) -> None:
        self._audio_host().skip_audio()

    def action_audio_pause(self) -> None:
        self._audio_host().toggle_audio_pause()

    def action_audio_stop(self) -> None:
        self._audio_host().stop_audio()

    def action_audio_seek(self, seconds: float) -> None:
        self._audio_host().seek_audio(seconds)

    def action_audio_seek_pct(self, percent: float) -> None:
        self._audio_host().seek_audio_percent(percent)

    def action_download(self) -> None:
        entry = self._playable_entry()
        if not entry:
            return
        from src.tui.screens.download_picker_modal import DownloadPickerModal

        def on_pick(result: tuple[str, str] | None) -> None:
            if result is not None:
                kind, fmt = result
                self._download(entry, audio_only=kind == "audio", fmt=fmt)

        self.app.push_screen(
            DownloadPickerModal(title=entry.get("title", entry.get("id", ""))), on_pick
        )

    def _download(self, entry: dict, *, audio_only: bool, fmt: str) -> None:
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

    def _open_channel(self, entry: dict) -> None:
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
        self.app.push_screen(ChannelScreen(channel_url=url, channel_name=name))

    def action_playlist(self) -> None:
        entry = self._playable_entry()
        if not entry:
            return
        from src.tui.screens.playlist_modal import PlaylistModal

        def on_done(_: None) -> None:
            self._detail().refresh_playlists(entry.get("id", ""))

        self.app.push_screen(PlaylistModal(entry), on_done)

    def action_copy_url(self) -> None:
        entry = self._selected_entry()
        vid = entry.get("id", "") if entry else ""
        if not vid or vid.startswith("__"):
            self.notify("No URL available", severity="warning")
            return
        url = watch_url(vid)
        if clipboard_copy(url):
            self.notify("URL copied to clipboard")
        else:
            self.notify(f"URL: {url}", timeout=10)

    def action_browser(self) -> None:
        entry = self._selected_entry()
        vid = entry.get("id", "") if entry else ""
        if vid and not vid.startswith("__"):
            webbrowser.open(watch_url(vid))
            self.notify("Opened in browser")
