# scripts/diagnose-rss.py

A report for one question: why does `https://www.youtube.com/feeds/videos.xml` fail on this network, and what does TermTube do about it. Run it, paste the output. Decision context: `docs/decisions/feeds-and-paging.md` (2026-11-15 entries), `docs/guides/benchmarks.md`.

- Anonymous and certificate-verified (the default `urllib` opener), `youtube.com` hosts only, about 30 small requests, no cookies, no media. A test asserts every URL host in the file is a YouTube host and that no request carries `Cookie` or `Authorization`.
- Sections: environment (Python, OpenSSL, which proxy variables are set by name, DNS), sanity (the home page and a made-up feed path, to tell "YouTube unreachable" from "feeds endpoint unreachable"), a matrix of URL forms (`channel_id`, `playlist_id` with `UU` and `UULF`, `http`, no `www`, `m.`) for three channels, a user-agent comparison, a verdict line, and the app path (`feeds._fetch_rss`, `feeds.channel_latest`, `innertube.fetch_channel_videos`, with counts, timings and which source won).
- Each probe line shows status, kind (`ATOM`, `HTML`, `other`), timing, redirect hops, selected headers (`server`, `via`, `x-cache`, `location`...) and the first 140 characters of the body. A 404 whose body is Google's generic page ("The requested URL ... was not found on this server") and an `ESF`/`gws` server header means YouTube answered; a proxy or filter usually shows a different `server` or `via`.
- It reads private names from `src.feeds` (`_fetch_rss`) on purpose, so the report matches what the app does.
- Tests: `src/tests/unit/test_diagnose_rss.py` (fake opener, no network).
