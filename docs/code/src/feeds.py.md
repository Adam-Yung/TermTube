# src/feeds.py

`channel_latest(channel_id)`: a channel's newest uploads from the public Atom feed (`/feeds/videos.xml`), falling back to `innertube.fetch_channel_videos`. Caller: `ChannelScreen._fetch_videos` (date sort only). The Subscriptions tab lists channels, not videos, so there is no merged subscription feed.

## Invariants

- Anonymous, stdlib `urllib` with certificate verification on. No `Cookie` or auth header; a test asserts it.
- RSS gives at most 15 entries and no duration. InnerTube gives about 30 with durations. RSS is first because it is the cheaper request when it works.
- `_DeadFlag` counts consecutive 404s (`_DEAD_AFTER_404S`, 2). At the threshold RSS is skipped for 30 minutes, so a dead feed costs two requests, not one per channel. Any non-404 response resets the count. Network errors neither count nor reset. The clock is injectable for tests. The state is module-level and guarded by a lock; workers share it.
- The response read is capped at 1 MB.

## Known limit

The benchmark saw HTTP 404 on every channel from the owner's network (`docs/guides/benchmarks.md`), so there the fallback is the normal path. The Atom fixture `src/tests/fixtures/channel_feed.xml` is hand-written from the documented feed format, not recorded.
