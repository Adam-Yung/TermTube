# src/tui/widgets/video_rows.py

The widgets the list mounts. Clicks are turned into private messages the panel handles, so a click on an unhighlighted row only moves the cursor. `_build_markup` reads the theme, falling back to crimson without an app config, and delegates to `row_markup`.
