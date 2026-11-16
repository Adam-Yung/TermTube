# src/tui/screens/download_picker_modal.py

Two-step picker: video or audio, then quality. Dismisses `(type, format)` or `None`. Esc on step 2 returns to step 1; Esc on step 1 cancels. Quality lists come from `src/downloads.py` (`QUALITY_CHOICES`) plus a local audio list. The accent colour is read from the app's `theme-*` class because list labels are Rich markup and cannot use the TCSS theme.
