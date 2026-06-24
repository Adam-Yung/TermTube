# Active Context

## Current Task: COMPLETED
Fixed yt-dlp performance bottlenecks (stream resolution and cold-start latency).

## What Was Done
- Split `_base_opts()` (with `skip: ['dash', 'hls']`) from `_playback_opts()` (no skip)
- `resolve_stream_url()` now uses `_base_opts` for audio-only (fast: ~1.9s) and `_playback_opts` for video (full DASH manifest access: ~2.4s)
- `download_video_with_progress()` and `download_audio_with_progress()` now use `_playback_opts` for proper format selection
- Added `warmup()` function in ytdlp.py — pre-initializes yt-dlp extractor registry
- Added background warmup thread in `TermTubeApp.on_mount()` to hide ~200-400ms init cost
- Stash now calls `panel.finish_loading()` immediately so users see content without waiting for network refresh

## Key Technical Notes
- The `skip: ['dash', 'hls']` extractor_arg was being applied to ALL yt-dlp calls, including stream resolution — this blocked DASH manifest parsing which is needed for format selection
- For audio-only format specs (e.g., `ba[format_note*=original]/ba`), the skip is actually fine since YouTube provides audio outside DASH
- For video format specs (e.g., `bv+(ba/ba)`), the skip was preventing proper quality selection and could cause resolution to pick suboptimal formats
- The warmup thread runs a throwaway `YoutubeDL({})` instance to trigger extractor loading before the first real call
