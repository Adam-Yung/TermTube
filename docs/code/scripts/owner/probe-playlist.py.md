# scripts/owner/probe-playlist.py

Not part of the gate. Records anonymous InnerTube replies for playlist pages so the playlist header parser and the Mix decision rest on real
responses ([decisions/playlist-page.md](../../../decisions/playlist-page.md)). Probes: a public playlist and a Topic (`OLAK…`) playlist found
through `innertube.search`, `browse VLRD<video>` and `next` for a Mix, `browse VLWL` for Watch Later, and optionally a private playlist id.

Rules it keeps (AGENTS.md allowlist): `www.youtube.com` only, one request at a time, 4 s apart, no retry, stop at the first 429, 403 or 5xx.
Output is JSON written to a new or empty `OUT_DIR`; the console shows where the header, alert and item renderers are. The recorded files become
fixtures under `src/tests/fixtures/` after they are trimmed by hand.
