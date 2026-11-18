# src/feed_cursor.py

One lazy, flat yt-dlp listing of an account feed (Home, History on YouTube, Watch Later) that is advanced in steps. The loader keeps one `FeedCursor` per loaded view, so the next batch continues where the last one stopped instead of re-reading the feed from the top and filtering `skip_ids`.

- `take(count, skip_ids, on_first_batch=, first_batch_size=)` opens the listing on first use (`lazy_playlist`, no `playlistend` below `MAX_FEED_ENTRIES`, 1000), then pulls rows until `count` playable, unskipped entries exist. Entries are cached like `_extract_videos` does (`put_video`); `ids` collects them for `cache.put_feed`. A feed that ends sets `exhausted`.
- Thread rules: `take` holds a lock, so the generator is only ever advanced by one thread at a time. `close()` may come from any thread (view change, quit): it sets the cursor's cancel event (registered with `ytdlp.new_cancel_event`, so `ytdlp.cancel_all` closes it too) and closes the extractor itself when no `take` runs; a running `take` stops before it reads the next row and closes the extractor as it returns.
- Errors: a `DownloadError` before any row retries once (2 s) and then raises the typed `SourceError` from `errors.classify` (a sign-in failure also drops the cookie jar, as `_extract_videos` does). After rows were read it returns them; the dead generator is dropped and the next `take` reopens the feed from the top, skipping `skip_ids`.
- Not exercised against YouTube: whether the live generator keeps paging across calls with the extractor left open is `[verify live]`; the tests use a fake extractor that records opens and reads.
- `FeedLoaderMixin._revalidate` also uses it: a stale-but-valid Home cache is read once behind the shown rows; the cursor then stays the view's cursor.
