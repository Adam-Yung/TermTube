# Configuration

One YAML file, created with defaults on first run. Nothing ships in the repo.

| | Path |
|---|---|
| macOS / Linux | `~/.config/TermTube/config.yaml` (`$XDG_CONFIG_HOME/TermTube/` if set) |
| Windows | `%APPDATA%\TermTube\config.yaml` |
| Elsewhere | `termtube --config FILE` |

History (`history.json`) and local playlists (`playlists.json`) sit next to it. In the app, Settings (`,`) edits theme, quality, thumbnail format and
browser; each choice is saved at once (there is no Save button). Unknown keys in the file are preserved on save. Edit the file freely while the app is closed.

## Keys

| Key | Default | Meaning |
|---|---|---|
| `browser` | `auto` | cookie source for Home and Subscriptions: `auto`, `none`, or a browser name. See [accounts-and-cookies.md](accounts-and-cookies.md) |
| `video_dir` | `~/Documents/TermTube/Video` | where video downloads go; also scanned by the Library tab |
| `audio_dir` | `~/Documents/TermTube/Audio` | where audio downloads go; also scanned by the Library tab |
| `video_format` | `%(title)s_%(uploader)s.%(ext)s` | yt-dlp output template for videos |
| `audio_format` | `%(title)s_%(uploader)s.%(ext)s` | yt-dlp output template for audio |
| `preferred_quality` | `best` | default video download quality: `best`, `1080`, `720`, `480`, `360` |
| `theme` | `crimson` | `crimson`, `amber`, `ocean` or `midnight` (anything else falls back to `crimson`) |
| `thumbnail_format` | `auto` | `auto`: real image where the terminal supports it; `symbols`: always half-block art. Anything else reads as `auto` |
| `thumbnail_warning_dismissed` | `false` | set by the "no image support" dialog's "Never show again" |
| `sponsorblock.enabled` | `true` | fetch skip segments for playback |
| `sponsorblock.auto_skip` | `true` | seek past a segment automatically |
| `sponsorblock.categories` | `[sponsor, selfpromo]` | SponsorBlock categories to skip (a non-list reads as the default) |
| `cache_ttl.home` | `3600` | seconds a cached Home feed stays fresh |
| `cache_ttl.subscriptions` | `3600` | reserved for a subscription video feed (the Subscriptions tab lists channels, cached with the 1 h default) |
| `cache_ttl.search` | `1800` | seconds a cached search stays fresh |
| `cache_ttl.metadata` | `86400` | seconds cached video metadata stays valid |
| `prefetch_video` | `false` | also pre-resolve a video stream URL when focusing a row (audio is always prefetched); no UI |

`cache_ttl` and `sponsorblock` merge one level deep: setting one sub-key keeps the other defaults.

## Rules

- Typed accessors validate (`theme`, `thumbnail_format`, `sponsorblock.categories`); raw `config["x"]` / `config.get` do not.
- Code changes a setting with `config.set(key, value)` and persists it with `config.save()`; nothing outside `src/config.py` touches `_data`.
- Tests construct `Config(path=<tmp file>)`; the default path is the real user config.
- `termtube --clear-cache` removes cached feeds and metadata; it never touches config, history or playlists.

Design record: `docs/decisions/config.md`; code: `docs/code/src/config.py.md`.
