# src/channel_bookmarks.py

Channels the user follows locally, in `channels.json` through `JsonStore` (version 1, a list of `{id, name, avatar, added}`). It exists so a followed-channels list works with `browser: none`, where the account-backed Subscriptions feed is empty. It does not touch YouTube, the account or the subscription cache.

- Only a `UC…` id is accepted (`channel_ref.is_channel_id`); a handle returns False and stores nothing, because the id is the stable key.
- `toggle` follows or unfollows in one store update and returns whether the channel is now followed. `entries` returns list rows (`_is_channel`, `channel_url`, the stored avatar as `thumbnail`), newest follow first, which is why `ChannelScreen` stores the avatar URL when it follows.
- Callers: `ChannelScreen.action_bookmark` (`B`) and `FeedLoaderMixin._load_following` (the Following view). Tests redirect the file with the `temp_channels` fixture.
