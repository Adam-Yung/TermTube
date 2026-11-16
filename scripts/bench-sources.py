#!/usr/bin/env python3
"""Time each rung of the source ladder (docs/plans/2026-11-15-optimization-PLAN.md) against public YouTube endpoints.

Anonymous: no cookies, no browser profile. Makes about 60 small requests plus a few yt-dlp metadata
resolves (no media is downloaded). Usage: scripts/bench-sources.py [runs]
"""
from __future__ import annotations

import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import innertube  # noqa: E402

VIDEOS = ["dQw4w9WgXcQ", "jNQXAC9IJRE", "9bZkp7q19f0"]
CHANNEL = "UCuAXFkgsw1L7xaCfnd5JJOw"
QUERY = "lofi hip hop"


def timed(fn, runs: int):
    samples, ok = [], 0
    for _ in range(runs):
        start = time.perf_counter()
        try:
            ok += bool(fn())
        except Exception:
            pass
        samples.append((time.perf_counter() - start) * 1000)
    return samples, ok


def get(url: str, *, method: str = "GET") -> bytes:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()


def search():
    data = innertube._post_json(
        "https://www.youtube.com/youtubei/v1/search?prettyPrint=false",
        {"query": QUERY, "context": innertube._WEB_CONTEXT},
    )
    return data and "contents" in data


def channel_browse():
    return innertube.fetch_channel_videos(CHANNEL, sort="date")


def ytdlp_resolve(video_id: str):
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "format": "ba/b"}) as ydl:
        return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False).get("url")


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    vid = VIDEOS[0]
    cases = [
        ("rung1 thumbnail GET (i.ytimg.com)", lambda: get(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"), runs),
        ("rung2 oEmbed", lambda: get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")), runs),
        ("rung2 channel RSS", lambda: get(f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}"), runs),
        ("rung3 InnerTube /player", lambda: innertube.fetch_video_details(vid), runs),
        ("rung3 InnerTube /search", search, runs),
        ("rung3 InnerTube /browse channel videos", channel_browse, runs),
        ("rung5 yt-dlp stream resolve", lambda: ytdlp_resolve(vid), min(runs, 3)),
    ]
    print(f"{'operation':44} {'n':>3} {'ok':>3} {'p50 ms':>8} {'max ms':>8}")
    for name, fn, n in cases:
        samples, ok = timed(fn, n)
        print(f"{name:44} {n:>3} {ok:>3} {statistics.median(samples):>8.0f} {max(samples):>8.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
