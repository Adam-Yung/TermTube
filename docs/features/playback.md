# Playback: audio and video

> Verified: 2026-11-28 · Sources: `src/tui/audio_controller.py`, `src/tui/audio_launch.py`, `src/tui/audio_queue.py`, `src/player.py`, `src/streams.py`, `src/tui/screens/watch_modal.py`, `src/progress.py`, `src/tui/screens/mixins/playlist_rows.py`
> Serves: `playback`
> Owns: `src/tui/audio_*.py`, `src/player.py`, `src/mpv_ipc.py`, `src/streams.py`, `src/sponsorblock.py`, `src/progress.py`, `src/playlist_fetch.py`, `src/tui/segment_skip.py`, `src/tui/screens/watch_*.py`, `src/tui/screens/queue_screen.py`, `src/tui/screens/quality_modal.py`, `src/tui/screens/mixins/audio_bar.py`, `src/tui/screens/mixins/playlist_rows.py`, `src/tui/widgets/segment_bar.py`

## What it does

Both go through **mpv**, driven by TermTube. Audio runs headless in the background and keeps playing while you browse; video opens an mpv window.

## Audio (`a`, `A`, `e`, `>`, `<`, `q`, `Space`, `x`, `[ ] { }`, `0`-`9`)

- One **audio controller** (`app.audio`, `src/tui/audio_controller.py`) owns the mpv process, the queue and the position polling for the whole app. Screens only
  mirror its state, so music survives opening a channel page, a menu or a download.
- `a` plays now (replacing the current track, keeping the queue); `A` asks for a quality first. `e` queues; with nothing playing it starts
  playback. `>` skips to the next queued track; `<` goes back to the track played before it (the current one returns to the head
  of the queue). The played tracks are forgotten by `x`, a new playlist and the end of the queue. `x` stops and clears the queue. The queue is in memory: quitting drops it.
- `q` opens the **queue page** from the main and channel pages (empty, with a hint, when nothing is queued): the playing track first with a
  `NOW PLAYING` badge, then the upcoming ones, with thumbnail and details beside the list. `J` `K` reorder the highlighted upcoming track,
  `D` removes it, `c` clears every upcoming track (the current one keeps playing), `u` undoes a remove or clear (until you leave the page),
  `Enter` or `a` plays it now (the tracks before it stay queued). `d` `y` `p` `b` and the transport keys work there too; `q`, `Esc` or
  `Backspace` goes back. The list follows the queue live. The playing track cannot be moved or removed: `>` skips it, `x` stops audio.
- A track is never both playing and queued: starting a queued track takes it out of the upcoming list.
- Pressing `a` on the track that is already playing says so instead of restarting it. `Space`, `x`, `>` with nothing playing, and `>` with an empty
  queue, say so too.
- **Where the audio comes from.** A YouTube video: the stream URL is resolved by yt-dlp (about 2 s; usually already cached because the row was
  prefetched when you paused on it), warmed against the CDN, and handed to mpv as a direct URL. A **local file** (Library, downloads): handed to mpv as a plain file.
- mpv is started with its own control channel (a Unix socket, or a named pipe on Windows) and polled every 0.5 s for position, length and pause
  state. Seeks and pause are commands on that channel. A second per-track channel name keeps a dying mpv from answering for the next track.
- **Failure handling.** If mpv exits abnormally it is relaunched up to three times, re-resolving the stream URL each time (the usual cause is an expired
  URL). After the third failure a notice says why (first line of mpv's stderr, translated for common cases) and the queue moves on.
- **SponsorBlock.** When enabled, skip segments for the video are fetched in the background (3 s timeout, cached a day) and the player seeks past
  a segment automatically (`auto_skip`). The progress bar marks the segments.
- **History.** A track enters History when mpv first reports a position, so a failed launch never leaves a row.
- **Resume.** The position is saved while you play (every 5 s of watching, and when you stop, switch tracks, close the player or quit). Playing the
  same video again, audio or video, from History or anywhere else, starts there and says "Resuming at 12:34". Nothing is resumed below 10 s, from
  95 % of the length (that counts as finished and clears the point), for live streams, or with `resume_playback: false`. To start over press `0`.
  History rows show `▶ 2:05 / 10:00`. It needs History on: no record, no resume.
- **Watch time.** `seconds` on the history record counts time actually played: pauses and seeks add nothing, and a step between two polls over 3 s
  is treated as a seek. `plays` counts starts. `s` on the local History tab sorts by recent (day headers), most watched (plays, then time) or longest
  watched; the sort lasts for the session and the other two orders have no day headers.
- Audio is refused with a hint for channel rows.

## Video (`v`, `V`)

- `v` opens an mpv window with the video and a small modal in the terminal showing progress and the same transport keys (`Space`, `h l`/arrows and
  `[ ]` seek 5 s, `H L` and `{ }` 10 s, `0`-`9`, `q`/`Esc` stop).
- Stream resolution, retries, SponsorBlock and resume work as for audio. A local file plays directly.
- **Playlist rows.** `v`, `a` and `e` on a playlist or Mix row (Search, Home, a channel's Playlists tab) or on a Library rail playlist
  act on the whole list without opening it: up to 200 videos are read first ("Loading the playlist…"), then `a` replaces the track
  and queue, `e` queues, `v` starts a video run. A result that arrives after another play, stop or playlist request is dropped.
- **Video run.** One mpv window per video, the header says "3 / 50". The end of a video starts the next; `>` / `<` step (terminal or
  mpv window); `q`, `Esc` or closing the window ends the run. A video that fails is skipped; three failures in a row end the run.
- **Video is refused while audio plays** (`v`, `V` and the menu entries): the two would overlap. Stop audio with `x` first.

## What can go wrong

| Notice | Meaning |
|---|---|
| `No headless mpv found` | mpv is not in the managed folder; run setup (`termtube --update`) |
| `✗ Audio failed: <title> (<reason>)` | three launches failed; `termtube --debug` writes mpv's own log beside the app log |
| `Resolving stream…` then nothing | yt-dlp could not resolve the video (age gate, removed, blocked); the debug log has the error |

## Where it lives

`src/tui/audio_controller.py` (state, threads, polling), `src/player.py` (mpv commands, IPC, the shared launch-and-retry loop `run_mpv_with_retries`),
`src/streams.py` (URL resolution and cache), `src/playlist_fetch.py` and
`src/tui/screens/mixins/playlist_rows.py` (playlist rows), `src/tui/screens/watch_modal.py` (video), `src/sponsorblock.py`. Mirrors under `docs/code/`; decisions in
`docs/decisions/playback.md`; the real thing exercised end to end by `scripts/e2e-local.py` ([../guides/ci.md](../guides/ci.md)).

## Rules that must hold

- A late launch, poll or completion of an old track never touches the new one (session counter).
- Stream resolution never uses account cookies.
- Video is refused while audio plays; a track is never both playing and queued.

## Limits

- The queue is in memory only. Video-run keys are tested against a headless mpv, not a real video window.

## How to check it

`src/tests/tui/test_audio_controller.py`, `src/tests/tui/test_queue.py`, `src/tests/tui/test_playlist_row_playback.py`, `src/tests/unit/test_run_mpv.py`, `src/tests/integration/test_mpv_ipc.py`.
