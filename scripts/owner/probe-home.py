#!/usr/bin/env python3
"""What does your signed-in Home hold? Counts the raw rows yt-dlp returns, by kind, and how many TermTube keeps.

Run by the owner only: it reads your browser cookies (the same way the app does) and makes one throttled request to
youtube.com. Prints counts and the first few playlist-like rows (id, title); no cookies or account data are printed.
Usage: scripts/owner/probe-home.py [--rows N]
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import yt_dlp

from src import flat_entries, ytdlp
from src.config import Config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=60)
    args = ap.parse_args()
    print("yt-dlp", yt_dlp.version.__version__)
    config = Config()
    opts = ytdlp._flat_opts(args.rows)
    opts.update(sleep_interval_requests=2)
    with ytdlp._make_ydl(opts, config, auth=True) as ydl:
        info = ydl.extract_info(ytdlp.FEED_URLS["home"], download=False)
    rows = list((info or {}).get("entries") or [])
    kinds = collections.Counter(
        (r.get("ie_key"), r.get("_type"), (r.get("url") or "")[:32].split("?")[0]) for r in rows
    )
    print(f"{len(rows)} raw rows")
    for kind, n in kinds.most_common():
        print(f"  {n:3d}  ie_key={kind[0]} _type={kind[1]} url={kind[2]}")
    kept = [flat_entries.playlist_row(r) for r in rows]
    kept = [k for k in kept if k]
    playable = sum(flat_entries.is_playable_video(r) for r in rows)
    print(f"kept as playlist rows: {len(kept)}; playable videos: {playable}")
    for k in kept[:5]:
        print("  playlist:", k["id"], k.get("title"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
