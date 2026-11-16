# src/tui/screens/mixins/item_actions.py

Actions on the highlighted row: watch, audio, download, channel, playlist, copy URL, open in browser, and the Enter menu (`VideoActionModal`). Bindings are `keymap.PLAYBACK` and `keymap.ITEM_ACTIONS`.

## Interface

- Audio keys call `self.app.audio` (`AudioController`), the one controller every screen shares, so music survives leaving the channel page. After `play_audio`/`enqueue_audio` the mixin calls `_sync_player_bar()` (`AudioBarMixin`) so the bar updates without waiting for the broadcast.
- `_hidden_menu_actions` hides "enqueue" when `can_enqueue` is false. `ChannelScreen` also hides "channel", since it is already there.
- `_playable_entry` filters out playlist and channel rows (`_is_playlist`, `_is_channel`). `copy_url` and `browser` use any entry with a real id (ids starting `__` are placeholders).
- `action_channel` builds the channel URL from `channel_url`, `uploader_url`, or an `@handle`/`UC` id. Also the target of the detail panel's `[@click=screen.channel]` link.
- `action_audio_seek(seconds)` and `action_audio_seek_pct(percent)` receive their argument from bindings such as `audio_seek(-5)`; keys are listed in `docs/features/keybindings.md`.

Video playback (`WatchModal`) suspends the app and runs mpv in the foreground (`docs/decisions/playback.md`); it does not go through `app.audio`.
