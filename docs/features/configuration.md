# Configuration

One YAML file, created with defaults on first run. Nothing ships in the repo.

| | Path |
|---|---|
| macOS / Linux | `~/.config/TermTube/config.yaml` (`$XDG_CONFIG_HOME/TermTube/` if set) |
| Windows | `%APPDATA%\TermTube\config.yaml` |
| Elsewhere | `termtube --config FILE` |

History (`history.json`) and local playlists (`playlists.json`) sit next to it. In the app, Settings (`,`) edits nearly every key below, in sections (Playback, Downloads, Data, Account, Display); the file path is shown at the top, and "Reload from disk" re-reads the file after a hand edit (a parse error is reported and the settings in memory stay). A refused value (unwritable directory, a name template with `..`, a number out of range) shows its reason instead of being saved; `Backspace` resets a row to its default. Each choice is saved at once (there is no Save button). Unknown keys in the file are preserved on save. Edit the file freely while the app is closed, or reload it from Settings.

## Keys

| Key | Default | Meaning |
|---|---|---|
| `browser` | `auto` | cookie source for Home and Subscriptions: `auto`, `none`, or a browser name. See [accounts-and-cookies.md](accounts-and-cookies.md) |
| `video_dir` | `~/Documents/TermTube/Video` | where video downloads go; also scanned by the Library tab |
| `audio_dir` | `~/Documents/TermTube/Audio` | where audio downloads go; also scanned by the Library tab |
| `video_format` | `%(title)s_%(uploader)s.%(ext)s` | yt-dlp output template for videos, relative to `video_dir`. Subfolders are fine; an absolute path or a `..` part is refused with an error in the download dialog |
| `audio_format` | `%(title)s_%(uploader)s.%(ext)s` | yt-dlp output template for audio, relative to `audio_dir`, same rules |
| `preferred_quality` | `best` | default video download quality: `best`, `1080`, `720`, `480`, `360` |
| `theme` | `crimson` | `crimson`, `amber`, `ocean` or `midnight` (anything else falls back to `crimson`) |
| `thumbnail_format` | `auto` | `auto`: real image where the terminal supports it; `symbols`: always half-block art. Anything else reads as `auto` |
| `insecure_thumbnails` | `false` | `true` lets a thumbnail download retry without certificate verification after a TLS error (TLS-inspecting proxies). Only a literal `true` counts |
| `thumbnail_warning_dismissed` | `false` | set by the "no image support" dialog's "Never show again" |
| `sponsorblock.enabled` | `true` | fetch skip segments for playback |
| `sponsorblock.auto_skip` | `true` | seek past a segment automatically |
| `sponsorblock.categories` | `[sponsor, selfpromo]` | SponsorBlock categories to skip (a non-list reads as the default); values: sponsor, selfpromo, interaction, intro, outro, preview, filler, music_offtopic, poi_highlight |
| `cache_ttl.home` | `3600` | seconds a cached Home feed stays fresh |
| `cache_ttl.home_revalidate` | `600` | seconds after which a cached Home feed is shown at once and re-read in the background (a non-integer or negative value means 600; no Settings row) |
| `cache_ttl.subscriptions` | `3600` | reserved for a subscription video feed (the Subscriptions tab lists channels, cached with the 1 h default); no Settings row until something reads it |
| `cache_ttl.search` | `1800` | seconds a cached search stays fresh |
| `cache_ttl.metadata` | `86400` | seconds cached video metadata stays valid |
| `history` | `true` | `false` records nothing in the local watch history (existing history stays until `--clear-history`); only a literal `false` turns it off |
| `search_history` | `true` | `false` stops recording searches and hides the history rows in the search prompt (existing queries stay until `--clear-history`); only a literal `false` turns it off |
| `search_suggestions` | `true` | `false` stops asking Google for search suggestions while you type (the partial text is sent to `suggestqueries.google.com`, anonymously); only a literal `false` turns it off. Settings modal has the toggle |
| `history_max` | `500` | most entries kept in the local history; clamped to 50..5000, a non-integer reads as 500 |
| `prefetch_video` | `false` | also pre-resolve a video stream URL when focusing a row (audio is always prefetched); only a literal `true` turns it on. Settings has the toggle |
| `resume_playback` | `true` | start a video or track where it stopped last time (History rows show `▶ 2:05 / 10:00`); only a literal `false` turns it off. Needs history on. Settings has the toggle |
| `rows_per_page` | `20` | entries per list page, clamped to 10..50 (a non-integer reads as 20). Applies at the next list load: switch tab, search again or refresh |

`cache_ttl` and `sponsorblock` merge one level deep: setting one sub-key keeps the other defaults.

## Rules

- Typed accessors validate (`theme`, `thumbnail_format`, `insecure_thumbnails`, `sponsorblock.categories`, `history`, `history_max`, `rows_per_page`, `prefetch_video`, `resume_playback`); raw `config["x"]` / `config.get` do not.
- Code changes a setting with `config.set(key, value)` (dotted keys such as `cache_ttl.home` work) and persists it with `config.save()`, which returns False when nothing was written; `config.reload()` re-reads the file. Nothing outside `src/config.py` touches `_data`.
- Tests construct `Config(path=<tmp file>)`; the default path is the real user config.
- `termtube --clear-cache` removes cached feeds and metadata; it never touches config, history or playlists.
- `termtube --clear-history` erases the local watch history and the search history file contents at once and exits; nothing else changes.

Design record: `docs/decisions/config.md`; code: `docs/code/src/config.py.md`.
