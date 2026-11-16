# src/tui/screens/mixins/item_actions.py

Actions on the highlighted row: watch, audio, download, channel, playlist, copy URL, open in browser, and the Enter menu (`VideoActionModal`). Bindings are `keymap.PLAYBACK` and `keymap.ITEM_ACTIONS`.

## Interface

- Audio keys call `self.app.audio` (`AudioController`), the one controller every screen shares, so music survives leaving the channel page. After `play_audio`/`enqueue_audio` the mixin calls `_sync_player_bar()` (`AudioBarMixin`) so the bar updates without waiting for the broadcast.
- `_hint(message, severity)` is the one way a key says it cannot act: a toast, shown at most once per 2 s per message so a held key does not stack notices. Used for: not a video (channel and playlist rows), already playing this track (`a`; `A` still works because it can change the format), nothing playing and empty queue (`Space`, `x`, `>`), live stream and fully downloaded (`d`), no URL (`y`, `b`), and the video-while-audio refusal. Look of the toasts: `docs/decisions/ui.md`.
- `_page_url(entry)` gives the YouTube page of a row for `y` and `b`: the watch URL, a channel's URL, or a playlist's `url`; empty for local placeholders (`__...` ids).
- `d` is refused for a live stream (`is_live` or `live_status`) and when the Library merged a video with its audio file (`_has_audio`). A video-only or audio-only local file still opens the picker.
- `_video_blocked_by_audio()` guards `action_watch_quality` and `_watch` (the one place both `v` and the menu and a finished quality pick go through): while `app.audio.is_playing` (including the 1-3 s resolving phase) it notifies and returns. `_hidden_menu_actions` also hides the two Watch entries then.
- With nothing playing the Enter menu shows the enqueue entry relabelled "Play audio, queue more after" (`_menu_labels`), because `e` starts playback when idle; while playing it is hidden only for the current or an already queued track.
- `_hidden_menu_actions` hides "enqueue" when `can_enqueue` is false. `ChannelScreen` also hides "channel", since it is already there.
- `_playable_entry` filters out playlist and channel rows (`_is_playlist`, `_is_channel`). `copy_url` and `browser` use any entry with a real id (ids starting `__` are placeholders).
- `action_channel` builds the channel URL from `channel_url`, `uploader_url`, or an `@handle`/`UC` id. Also the target of the detail panel's `[@click=screen.channel]` link.
- `action_audio_seek(seconds)` and `action_audio_seek_pct(percent)` receive their argument from bindings such as `audio_seek(-5)`; keys are listed in `docs/features/keybindings.md`.

Video playback (`WatchModal`) suspends the app and runs mpv in the foreground (`docs/decisions/playback.md`); it does not go through `app.audio`.
