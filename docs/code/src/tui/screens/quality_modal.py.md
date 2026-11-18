# src/tui/screens/quality_modal.py

Format picker opened by `V` (video) and `A` (audio). Dismisses a yt-dlp format string or `None`. Choices are `downloads.QUALITY_CHOICES` / `AUDIO_QUALITY_CHOICES`.

Settings reuses it as a generic picker: `choices` (`(label, value)` rows), `title` and `current` (the active value gets a `▶` marker and the cursor starts on it). Without `choices` it behaves as before.
