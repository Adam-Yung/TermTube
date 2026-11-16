from __future__ import annotations

from src.entries import Entry
from src.tui.messages import AudioQueueChanged, AudioSegmentsLoaded, AudioTrackChanged, PlayerStateUpdated


class AudioBarMixin:
    """Mirrors ``app.audio`` into this screen's ``ActionBar``.

    Needs ``_detail()`` (``DetailFocusMixin``) and ``_selected_entry()`` (``ListNavMixin``).
    A screen created while audio plays calls ``_sync_player_bar`` once; after that the controller's
    messages keep the bar current, including while another screen covers this one.
    """

    def _sync_player_bar(self) -> None:
        audio = self.app.audio
        bar = self._detail().action_bar
        if audio.is_playing and audio.entry:
            bar.set_player_mode(audio.entry, queue_len=len(audio.queue))
            bar.set_segments(audio.segments)
            if audio.progress:
                bar.update_progress(*audio.progress)
            self._refresh_queue_hint()
        elif not audio.is_playing:
            bar.set_actions_mode()

    def _refresh_queue_hint(self, focused_entry: Entry | None = None) -> None:
        """Hide the enqueue hint when the focused row is already playing or queued."""
        try:
            bar = self._detail().action_bar
        except Exception:
            return
        audio = self.app.audio
        entry = focused_entry or self._selected_entry()
        focused_id = entry.get("id") if entry else None
        playing_id = (audio.entry or {}).get("id")
        queued = {e.get("id") for e in audio.queue}
        bar.update_queue_hint(
            len(audio.queue),
            hide_e=bool(focused_id and (focused_id == playing_id or focused_id in queued)),
        )

    def on_audio_track_changed(self, message: AudioTrackChanged) -> None:
        bar = self._detail().action_bar
        bar.set_player_mode(message.entry, queue_len=message.queue_len)
        bar.set_segments([])
        self._refresh_queue_hint()

    def on_audio_queue_changed(self, message: AudioQueueChanged) -> None:
        self._refresh_queue_hint()

    def on_audio_segments_loaded(self, message: AudioSegmentsLoaded) -> None:
        self._detail().action_bar.set_segments(message.segments)

    def on_player_state_updated(self, message: PlayerStateUpdated) -> None:
        bar = self._detail().action_bar
        if message.playing:
            bar.update_progress(message.pos, message.dur, message.paused)
        else:
            bar.set_actions_mode()
