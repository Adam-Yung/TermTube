# src/tui/views.py

View ids and the tab each belongs to, the one place screens and mixins read them. A new tab or list source starts here, then gets its loader (`list_sources.py` or `feed_loader.py`), its rail entries (`library_rail.py`) and, in `main_screen.py`, its label, tools and removal.
