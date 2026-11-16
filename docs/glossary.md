# Glossary

| Term | Meaning |
|---|---|
| Entry | The dict describing one row: a video, a channel (`_is_channel`), a playlist (`_is_playlist`) or a library file (`_local_path`). |
| Page | 20 entries (`PAGE_SIZE`). The list shows one page; `h`/`l` move between pages. |
| Stash | The 20 unseen home-feed entries saved on exit and shown as page 1 on the next launch, before any network call. |
| Suppression | Videos focused 3+ times or played are hidden from future home feeds (LRU list in `cache.py`). |
| Dwell | The 100 ms / 150 ms pause after a cursor move before the metadata fetch / thumbnail render starts. |
| Session counter | An integer a worker captures at start; a result whose counter is stale is dropped. Used for focus, thumbnail, avatar and audio. |
| Worker group | The `group=` of a Textual `@work`. `exclusive=True` cancels the older worker of the same group on the same node. |
| Audio host | The screen that owns the background mpv process: always `MainScreen`. |
| InnerTube | YouTube's internal JSON API (`/youtubei/v1/...`). `src/innertube.py`. |
| Source ladder | The ordering of data sources from cache to yt-dlp. `docs/plans/2026-11-15-optimization-PLAN.md`. |
| Mirror | The `docs/code/<path>.md` file for a source file. |
