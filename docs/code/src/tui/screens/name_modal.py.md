# src/tui/screens/name_modal.py

One-line name prompt used by playlist new and rename. Dismisses with the trimmed name, or `None` on Esc or an empty name. It reuses the
playlist dialog's ids and the shared `dialog` class, so it is centered and styled exactly like the other prompts; the caller decides what a duplicate means.
