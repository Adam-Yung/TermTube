# `scripts/bench-sources.py`

Times the ladder rungs from `docs/features/sources.md` and prints p50 and max per operation. Results and what they mean:
`docs/guides/benchmarks.md`.

- `--streams` times only the yt-dlp resolve variants (fresh, warmed and reused, `140/251`, manifest skip, `player_client` choices) with the production options from `ytdlp.base_opts`. A variant's `ok` column matters more than its time: clients that need a PO token fail fast and look quick.
- Each stream variant is a zero-argument callable that resolves the next sample video, so `timed` treats all variants alike.
- Anonymous only. It never reads cookies or a browser profile and downloads no media. The yt-dlp row does a metadata resolve (`ba/b`) and
  stops at the stream URL.
- It reuses `src.innertube._post_json` and `_WEB_CONTEXT`, so it measures the same requests the app makes. It imports a private name on
  purpose: the benchmark must stay in step with the client.
- It does not disable TLS verification. Behind a TLS-inspecting proxy the `i.ytimg.com` row fails and shows `ok 0`; that is a result, not a
  bug in the script.
- A row with `ok` below `n` has failed requests; its timings are of the failures. Check `ok` first.
