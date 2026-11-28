# src/tui/audio_launch.py

The `audio-launch` thread of `AudioController`: resolve the stream (or use `_local_path`), wait up to 2 s for SponsorBlock, run a headless mpv with retries, report the outcome. Session rules: `audio_controller.py.md`.

- `_socket_for(session)` lives here so the launch thread and the controller share one rule; the base path is cached once per process.
- `_AudioCommand` is called once per attempt. From the second attempt it re-resolves the stream URL and keeps the old one when that fails; local files are never re-resolved.
- UI work goes through `app.call_from_thread`. `_launch_worker` catches everything: an escaped exception would leave the bar on "Buffering" forever.
