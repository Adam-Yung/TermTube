# src/tui/widgets/row_markup.py

`row_markup` handles five row kinds: channel (Subscriptions), playlist, Local folder (`_is_folder`, `📁 FOLDER`), library or local file (badges from `_local_type`/`_has_audio`) and video. The `_is_*` and `_local_*` keys are set by the loaders and `library.py`.

A row flagged `_missing_file` shows a red `⚠ file missing` badge instead of the video/audio badge.

`set_playing(id)` badges that row as now playing (the queue page); it is a panel attribute, not an entry key, so nothing leaks into the cache.

A row with `_yt` (account list) or `source == "yt"` (imported into local history) shows a `YT` badge after the download badges.

History rows (records with `resume_s`, `plays`) add `▶ 2:05 / 10:00` (where playback resumes, over the length) and `×N` (plays, from the second) to the meta line. Both come from fields already on the row, so a list of thousands pays two dict lookups per row.

Rows with `_dl` (playlist items) show a download badge: `⬇ video`, `⬇ audio`, `⬇ both` or `☁` for stream only.

Badge priority is the order of `_badge_key`: playing, missing file, playlist, download state, local form, YouTube.
