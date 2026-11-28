# src/innertube_rows.py

Turns one InnerTube list item (video, `lockupViewModel`, Short, Mix panel row, search channel or playlist) into a TermTube entry, plus
the text and number parsing that needs. No network. Callers: `src/innertube.py` and `src/innertube_pages.py`.

- A `channel_id` and `channel_url` are set from a byline only for a real `UC...` id.
- Count and duration texts are the localized English ones (`hl: en`); anything else parses to None.
- Layout notes and fixtures are in `docs/code/src/innertube.py.md`.
