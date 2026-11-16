# src/tui/widgets/channel_info_panel.py

Left column of `ChannelScreen`: avatar (`ThumbnailWidget`), name, subscriber count, URL, description (capped at 2000 characters). `ChannelScreen` fills it from `ytdlp.fetch_channel_info`.

The avatar is keyed by an id derived from the channel (`ChannelScreen._avatar_id`, prefix `ch_`), not by a video id. The thumbnail widget drops results whose id differs, so a reload of another channel cannot paint over this one.

`info` keeps the last dict passed to `update_info`. `ChannelScreen._channel_id` reads it to find the `UC...` id for the InnerTube browse.
