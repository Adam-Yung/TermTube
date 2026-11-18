# src/tui/screens/mixins/item_actions.py

Actions on the highlighted row: watch, audio, download, channel, playlist, copy URL, open in browser, and the Enter menu (`VideoActionModal`). Bindings are `keymap.PLAYBACK` and `keymap.ITEM_ACTIONS`.

## Interface

- Audio keys call `self.app.audio` (`AudioController`), the one controller every screen shares, so music survives leaving the channel page. After `play_audio`/`enqueue_audio` the mixin calls `_sync_player_bar()` (`AudioBarMixin`) so the bar updates without waiting for the broadcast.
- `_hint(message, severity)` is the one way a key says it cannot act: a toast, shown at most once per 2 s per message so a held key does not stack notices. Used for: not a video (channel and playlist rows), already playing this track (`a`; `A` still works because it can change the format), nothing playing and empty queue (`Space`, `x`, `>`), live stream and fully downloaded (`d`), no URL (`y`, `b`), and the video-while-audio refusal. Look of the toasts: `docs/decisions/ui.md`.
- `_page_url(entry)` gives the YouTube page of a row for `y` and `b`: the watch URL, a channel's URL, or a playlist's `url`; empty for local placeholders (`__...` ids).
- `d` is refused for a live stream (`is_live` or `live_status`) and when the Library merged a video with its audio file (`_has_audio`). A video-only or audio-only local file still opens the picker.
- `_video_blocked_by_audio()` guards `action_watch_quality` and `_watch` (the one place both `v` and the menu and a finished quality pick go through): while `app.audio.is_playing` (including the 1-3 s resolving phase) it notifies and returns. `_hidden_menu_actions` also hides the two Watch entries then.
- With nothing playing the Enter menu shows the enqueue entry relabelled "Play audio, queue more after" (`_menu_labels`), because `e` starts playback when idle; while playing it is hidden only for the current or an already queued track.
- `_hidden_menu_actions` hides `audio_enqueue` when `can_enqueue` is false, the playback, download and playlist rows for a missing file, and `download` for a live stream or an item already downloaded as video and audio. `ChannelScreen` also hides "channel", since it is already there. The menu dispatches `action_<name>` from the action name in `keymap.ROW_ACTIONS`; there is no separate table.
- `_playable_entry` filters out playlist and channel rows (`_is_playlist`, `_is_channel`). `copy_url` and `browser` use any entry with a real id (ids starting `__` are placeholders).
- `action_channel` builds the channel URL from `channel_url`, `uploader_url`, or an `@handle`/`UC` id. Also the target of the detail panel's `[@click=screen.channel]` link.
- `action_audio_seek(seconds)` and `action_audio_seek_pct(percent)` receive their argument from bindings such as `audio_seek(-5)`; keys are listed in `docs/features/keybindings.md`.

Video playback (`WatchModal`) suspends the app and runs mpv in the foreground (`docs/decisions/playback.md`); it does not go through `app.audio`.

`_playable_entry` refuses a Library row flagged `_missing_file` with a hint to press `D`.
- `_open_channel` passes `_crumbs()` (the breadcrumb trail of the screen it was opened from; the screen provides it) to `ChannelScreen`. `MainScreen` returns its tab label, `ChannelScreen` its own trail plus its channel name. `ChannelScreen` hides "channel" only for rows of its own channel.

`panel_hints()` feeds the Actions panel (`ActionBar._action_entries`): Enter and the row actions for the highlighted row (a playlist or channel row only gets copy URL and browser), then `keymap.tool_hints(_tool_actions())`. A screen overrides `_tool_actions` to say which tools apply (`MainScreen`: by tab, removal support, rail focus, undo; `ChannelScreen`: follow, and play/queue/save inside a playlist) and calls `_refresh_actions` when the row, the focus or the tab changes.
