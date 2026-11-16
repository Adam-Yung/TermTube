#!/usr/bin/env python3
"""Time each rung of the source ladder (docs/plans/2026-11-15-optimization-PLAN.md) against public YouTube endpoints.

Anonymous: no cookies, no browser profile. Makes about 60 small requests plus a few yt-dlp metadata
resolves (no media is downloaded).
Usage: scripts/bench-sources.py [runs] [--streams]  (--streams times only the yt-dlp resolve variants)
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

VIDEOS = ["dQw4w9WgXcQ", "kJQP7kiw5Fk", "9bZkp7q19f0"]
CHANNEL = "UCuAXFkgsw1L7xaCfnd5JJOw"
QUERY = "lofi hip hop"
OEMBED = "https://www.youtube.com/oembed?format=json&url="


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
    return innertube.fetch_channel_videos(CHANNEL)


def _stream_opts(fmt: str, client: str | None, skip_manifests: bool) -> dict:
    from src.ytdlp import base_opts

    opts = base_opts(skip_manifests=skip_manifests)
    opts["format"] = fmt
    if client:
        opts.setdefault("extractor_args", {}).setdefault("youtube", {})["player_client"] = [client]
    return opts


def _resolved(info) -> bool:
    return bool(info and (info.get("url") or info.get("requested_formats")))


def ytdlp_resolve(video_id: str, fmt: str = "ba/b", client: str | None = None, skip_manifests: bool = False):
    import yt_dlp

    with yt_dlp.YoutubeDL(_stream_opts(fmt, client, skip_manifests)) as ydl:
        return _resolved(ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False))


def stream_variants(runs: int) -> None:
    """Time yt-dlp stream-resolve variants over the sample videos (slow: about 3 s per resolve)."""
    import yt_dlp

    def fresh(**kw):
        ids = iter(VIDEOS * runs)
        return lambda: ytdlp_resolve(next(ids), **kw)

    def warmed():
        ydl = yt_dlp.YoutubeDL(_stream_opts("ba/b", None, False))
        ydl.extract_info(f"https://www.youtube.com/watch?v={VIDEOS[0]}", download=False)
        ids = iter(VIDEOS * runs)
        return lambda: _resolved(ydl.extract_info(f"https://www.youtube.com/watch?v={next(ids)}", download=False))

    cases = [
        ("baseline: fresh YoutubeDL, ba/b", fresh()),
        ("(a) warmed reused YoutubeDL, ba/b", warmed()),
        ("(b) format 140/251", fresh(fmt="140/251")),
        ("skip dash+hls manifests", fresh(skip_manifests=True)),
        *[(f"(c) player_client={c}", fresh(client=c)) for c in ("web_safari", "tv", "ios", "mweb")],
    ]
    print(f"{'yt-dlp variant':44} {'n':>3} {'ok':>3} {'p50 ms':>8} {'max ms':>8}")
    for name, fn in cases:
        samples, ok = timed(fn, runs * len(VIDEOS))
        print(f"{name:44} {len(samples):>3} {ok:>3} {statistics.median(samples):>8.0f} {max(samples):>8.0f}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    runs = int(args[0]) if args else 5
    if "--streams" in sys.argv:
        stream_variants(runs)
        return 0
    vid = VIDEOS[0]
    cases = [
        ("rung1 thumbnail GET (i.ytimg.com)", lambda: get(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"), runs),
        ("rung2 oEmbed", lambda: get(OEMBED + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}")), runs),
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
