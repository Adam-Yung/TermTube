#!/usr/bin/env python3
"""Does live YouTube still look the way TermTube's parsers expect? Anonymous, youtube.com only, about 12 requests.

Not part of the gate: YouTube changes without notice and datacenter addresses are sometimes blocked, so a red
canary means "look", not "the code broke". Run by .github/workflows/canary.yml weekly and by hand.
Exit 0 only if every check passed.
Usage: scripts/canary-live.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import innertube

CHANNEL = "UC_x5XG1OV2P6uZZ5FSM9Ttw"  # Google Developers
VIDEO = "dQw4w9WgXcQ"
failures: list[str] = []


def check(name: str, ok: bool, detail: str, started: float) -> None:
    ms = (time.perf_counter() - started) * 1000
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail} ({ms:.0f} ms)", flush=True)
    if not ok:
        failures.append(name)


def main() -> int:
    t = time.perf_counter()
    results = innertube.search("lofi hip hop", count=10, kind="video")
    complete = [r for r in results if r.get("id") and r.get("title") and r.get("channel_id")]
    check("InnerTube search", len(complete) >= 5, f"{len(complete)} of {len(results)} rows complete", t)

    t = time.perf_counter()
    videos = innertube.fetch_channel_videos(CHANNEL)
    timed = [v for v in videos if v.get("duration")]
    check("InnerTube channel videos", len(videos) >= 10 and len(timed) >= len(videos) // 2,
          f"{len(videos)} videos, {len(timed)} with a duration", t)

    t = time.perf_counter()
    playlists = innertube.fetch_channel_playlists(CHANNEL, count=20)
    well_formed = all(p.get("id", "").startswith("PL") for p in playlists)
    check("InnerTube channel playlists", len(playlists) >= 3 and well_formed, f"{len(playlists)} playlists", t)

    t = time.perf_counter()
    page = innertube.fetch_playlist_page(playlists[0]["id"]) if playlists else innertube.ChannelPage([])
    pinfo = page.info or {}
    check("InnerTube playlist page", len(page.entries) >= 1 and bool(pinfo.get("title")),
          f"{len(page.entries)} rows, header {pinfo.get('title')!r}", t)

    t = time.perf_counter()
    mix = innertube.fetch_mix_page(f"RD{VIDEO}")
    check("InnerTube Mix (next)", len(mix.entries) >= 10 and bool(mix.token), f"{len(mix.entries)} rows", t)

    t = time.perf_counter()
    info = innertube.fetch_channel_info(f"https://www.youtube.com/channel/{CHANNEL}")
    check("InnerTube channel info", bool(info and info.get("channel") and info.get("subscriber_count")),
          f"{(info or {}).get('channel')!r}, {(info or {}).get('subscriber_count')} subscribers", t)

    t = time.perf_counter()
    details = innertube.fetch_video_details(VIDEO)
    check("InnerTube video details", bool(details and details.get("title") and details.get("duration")),
          f"{(details or {}).get('title')!r}", t)

    t = time.perf_counter()
    from src import streams

    urls = streams.resolve_stream_url(VIDEO, None, "ba/b")
    check("yt-dlp stream resolve", bool(urls and urls[0].startswith("http")), f"{len(urls or [])} url(s)", t)

    print(f"\n{'OK: YouTube still looks as expected' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
