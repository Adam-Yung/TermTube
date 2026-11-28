# src/innertube_pages.py

Reads whole InnerTube replies, no network: grid items and continuation tokens, the playlist and channel headers, the /player details,
search result sections and Mix pages. Caller: `src/innertube.py`, which documents the endpoints and shapes (`docs/code/src/innertube.py.md`).

Every field is optional: YouTube moves blocks around, so a missing piece is an empty string or None, never an error.
