# src/tui/fmt.py

Pure display formatters shared by the video list and the detail panel. Each returns `""` for missing or invalid input, so callers
join non-empty parts without checks.

- `fmt_age` takes yt-dlp's `YYYYMMDD` `upload_date` and measures against the local date. It returns `""` for a future date.
- Buckets are approximate: weeks under 30 days, months of 30 days, years of 365.
- `fmt_views` rounds 1,000 to 999,999 to whole K and larger values to one decimal.
- `fmt_subscribers` returns the bare number (`1.2M`, `340K`); the caller appends the noun.
