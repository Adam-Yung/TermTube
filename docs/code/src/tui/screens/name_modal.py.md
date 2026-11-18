# src/tui/screens/name_modal.py

One-line name prompt used by playlist new and rename. Dismisses with the trimmed name, or `None` on Esc or an empty name. It reuses the
playlist dialog's ids so `theme.tcss` styles it; the caller decides what a duplicate means.
