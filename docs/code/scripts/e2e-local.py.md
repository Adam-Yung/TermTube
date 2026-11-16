# scripts/e2e-local.py

The end-to-end check: the real app, in a real pseudo-terminal, playing real audio through a real mpv, with no network. A green run means the app starts, renders, scans the library, starts and controls mpv, records history and quits cleanly on this platform. Used by the `real app` CI jobs (`docs/guides/ci.md`) and by hand: `scripts/e2e-local.py` on a dev machine runs it silently against the checkout.

## What it does

1. Makes a private workdir with a config (`browser: none`, local `audio_dir`), a 30 s generated WAV with an `.info.json` sidecar (a Library entry), a private cache (`TERMTUBE_CACHE_DIR`), config (`XDG_CONFIG_HOME` or `APPDATA`), IPC directory (`XDG_RUNTIME_DIR`) and an `mpv.conf` with `ao=null`, so it is silent and needs no audio device. Nothing touches the user's own config, cache or sockets.
2. Seeds the Home feed through the app's own `Cache` (`put_video`, `put_feed`, `put_home_stash`). With a stash and a fresh feed cache the Home tab shows rows without any network request, so no `EmptyFeedModal` or update prompt can appear.
3. Launches the app (`python src/main.py --config ...`, or `--launcher` for the installed `termtube` / `termtube.cmd`) on a pty (stdlib `pty` on macOS and Linux, `pywinpty`/ConPTY on Windows), 130x40, and presses keys: `F5` (Library), `a`, `Space` twice, `]`, `x`, `F4` (History), `q`.
4. Checks two things at every step: the screen (text printed since the step began, with ANSI removed) and mpv itself over the app's IPC socket or pipe (`player.poll_audio_properties`): started and answering, advancing, paused then playing, a real +5 s jump within 3 s (natural playback adds at most about 3 s, so only a seek passes), gone after `x`, none left after quit, history shows the track, exit code 0.

## Notes

- The child's `COLUMNS` and `LINES` are pinned to the pty size (130x40). They override the pty's real size for Textual and for `shutil.get_terminal_size`, and a parent such as pytest sets them to 80x24; without the pin the app drew an 80x24 layout with no action bar and three screen steps failed while mpv steps passed.
- `--app-dir` is both where the app is launched from and where `src` is imported for seeding and IPC, so the installed copy tests itself. On Windows the harness must run in a Python with `pywinpty` and `pywin32` (the CI job installs `pywinpty` into the installed venv).
- Each assertion was shown to fail when the matching behaviour is broken (seek disabled, pause disabled, history disabled, stop not killing mpv, an import error at startup). The first version of the seek step passed with seek disabled because the tone advanced 4 s by itself; the threshold and window exist for that reason.
- Not covered by design: YouTube (see `canary-live.py`), thumbnails (the terminal has no image protocol), the look of the UI.
- Marks are positions in the raw output, not a screen model: Textual redraws only changed cells, so a step asserts that text appeared after the key, never that text disappeared.
