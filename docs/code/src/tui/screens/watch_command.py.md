# src/tui/screens/watch_command.py

Builds the foreground player's mpv command. Resolved URLs are passed directly with `--no-ytdl` (a second URL is the audio file); without URLs mpv resolves the page URL with the format and cookie options.

`VideoCommand` is the `build_cmd` of `run_mpv_with_retries`: from attempt 2 it asks for fresh URLs and keeps the previous ones when there are none. A local file has no `refresh`.

- A local file played directly gets `player.source_args` (`--access-references=no`), see `player.py.md`.
