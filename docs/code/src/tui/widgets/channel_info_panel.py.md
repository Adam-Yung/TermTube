# src/tui/widgets/channel_info_panel.py

Left column of `ChannelScreen`: avatar (`ThumbnailWidget`), name, subscriber count, a stats line ("442 videos · Joined Mar 3, 2011", whichever the info has), URL, and the description. `ChannelScreen` fills it from `ytdlp.fetch_channel_info`.

The description starts in full (the column normally has room); `toggle_description` (the `i` key) folds it to its first three lines (each cut at 120 characters) with a `i  show all` hint, and returns False when there is nothing more to show. Every `update_info` expands it again, so a reload or another channel starts in full. The full text is capped at 2000 characters.

The avatar is keyed by an id derived from the channel (`ChannelScreen._avatar_id`, prefix `ch_`), not by a video id. The thumbnail widget drops results whose id differs, so a reload of another channel cannot paint over this one.

`info` keeps the last dict passed to `update_info`. `ChannelScreen._channel_id` reads it to find the `UC...` id for the InnerTube browse.
