# src/tui/fmt.py

Pure display formatters shared by the video list and the detail panel. Each returns `""` for missing or invalid input, so callers
join non-empty parts without checks.

- `escape_markup` backslash-escapes every `[` so entry text (titles, channel names, descriptions) renders literally when embedded in Rich/Textual markup. `textual.markup.escape` leaves a lone `[` alone and lets it eat the following closing tag. Every widget that interpolates entry text into markup must use it (list rows, action bar, detail and channel panels, watch, action, download and playlist modals).
- `fmt_clock` is the one `H:MM:SS` / `M:SS` formatter (zero gives `0:00`; the action bar and the watch modal use it for the playback position). `fmt_duration` is `fmt_clock` that returns `""` for a missing or zero length.
- `fmt_age` takes yt-dlp's `YYYYMMDD` `upload_date` and measures against the local date. It returns `""` for a future date.
- Buckets are approximate: weeks under 30 days, months of 30 days, years of 365.
- `fmt_day_group` is the History day header: `Today`, `Yesterday`, `Mon 9 Nov` (year added for another year), `Earlier` for a row without `watched_at`.
- `fmt_views` rounds 1,000 to 999,999 to whole K and larger values to one decimal.
- `fmt_subscribers` returns the bare number (`1.2M`, `340K`); the caller appends the noun.

`fmt_size(n)` formats bytes (`812 B`, `1.4 KB`, `120 MB`).
