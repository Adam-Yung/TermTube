# Active Context

## Current Task: COMPLETED
Stream URL pre-resolution for instant playback.

## What Was Done
- Added stream URL cache in `src/ytdlp.py` (dict keyed by `vid:format`, 5h TTL, 20-entry cap)
- Added `prefetch_stream_url()` function that resolves and caches a URL (no-op if already cached)
- Added `_prefetch_stream_worker` in MainScreen that fires after InnerTube metadata fetch
- Modified `_launch_audio_worker` and `WatchModal._launch_video` to check cache before resolving
- Fixed video playback audio (--audio-file for split streams)
- Fixed feed cache performance (skip network when stash + cache fresh)
- Added auto cookie refresh after yt-dlp updates

## Key Technical Notes
- InnerTube /player API does NOT return streaming data without Proof of Origin token (JS challenge needed)
- Stream URL pre-resolution must still use yt-dlp (via Deno JS challenge solver)
- The optimization is temporal: resolve in background during browse time, so it's ready on play
- Audio resolution uses fast path (~1.9s with skip DASH/HLS), video uses full path (~2.4s)
- CDN URLs expire in ~6h; cache TTL set to 5h to stay safe
