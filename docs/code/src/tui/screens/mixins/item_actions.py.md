# src/tui/screens/mixins/item_actions.py

Actions on the highlighted row: watch, audio, download, channel, playlist, copy URL, open in browser, and the Enter menu (`VideoActionModal`). Bindings are `keymap.PLAYBACK` and `keymap.ITEM_ACTIONS`.

## Interface

- `_audio_host()` returns the object that owns audio (`AudioPlayerMixin` interface). `MainScreen` returns itself; `ChannelScreen` returns the `MainScreen` below it in the screen stack, because the mpv process and queue must survive leaving the channel page. Audio keys on the channel page therefore act on the main screen's player.
- `_sync_player_bar()` is a hook. After `play_audio`/`enqueue_audio` the screen showing the list copies the host's state into its own action bar. `MainScreen` needs nothing (the host is the screen); `ChannelScreen` implements it.
- `_hidden_menu_actions` hides "enqueue" when `can_enqueue` is false. `ChannelScreen` also hides "channel", since it is already there.
- `_playable_entry` filters out playlist and channel rows (`_is_playlist`, `_is_channel`). `copy_url` and `browser` use any entry with a real id (ids starting `__` are placeholders).
- `action_channel` builds the channel URL from `channel_url`, `uploader_url`, or an `@handle`/`UC` id. Also the target of the detail panel's `[@click=screen.channel]` link.
- `action_audio_seek(seconds)` and `action_audio_seek_pct(percent)` receive their argument from bindings such as `audio_seek(-5)`; keys are listed in `docs/features/keybindings.md`.

Video playback (`WatchModal`) suspends the app and runs mpv in the foreground (`docs/decisions/playback.md`); it does not go through the audio host.
