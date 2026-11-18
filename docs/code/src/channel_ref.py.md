# src/channel_ref.py

The one reader of YouTube channel URLs. `parse` returns `(form, value)` for `/channel/UC…`, `/@handle`, `/c/…` and `/user/…`
(anything after the first path segment is ignored, so `/videos` and query strings do not matter), or None. `channel_id` answers only for
the `id` form: a handle or legacy name needs a network lookup (`innertube.resolve_channel_id`), and this module never does one.

Callers: `innertube.resolve_channel_id` (skips the lookup when the URL has the id) and `ChannelScreen._channel_id`.
The id must be `UC` plus 22 characters; a shorter id is treated as no id, so a malformed URL falls through to the yt-dlp path.
