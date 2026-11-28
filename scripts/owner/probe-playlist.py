#!/usr/bin/env python3
"""Records what anonymous InnerTube returns for playlist pages, so the parser is built from real responses.

Run by the owner, or by an agent under the youtube.com allowlist in AGENTS.md. About 8 requests to www.youtube.com,
one at a time, 4 s apart, no retries; it stops at the first 429, 403 or 5xx. Raw responses go to OUT_DIR (new or
empty) as JSON data only; nothing in it is executed. Per probe it prints the status, size, top-level keys and the
header-like, alert and item renderer names with their counts.
Usage: scripts/owner/probe-playlist.py OUT_DIR [--playlist ID] [--topic OLAK...] [--private ID] [--mix-video VIDEOID]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src import innertube

PAUSE_S = 4
BASE = "https://www.youtube.com/youtubei/v1"
INTEREST = ("header", "microformat", "sidebar", "metadata", "alert", "message", "playlistVideoRenderer",
            "lockupViewModel", "playlistPanelVideoRenderer", "continuationItemRenderer")


class Blocked(Exception):
    pass


def post(endpoint: str, payload: dict) -> tuple[int, dict | None]:
    body = {**payload, "context": innertube._WEB_CONTEXT}
    req = urllib.request.Request(f"{BASE}/{endpoint}?prettyPrint=false", json.dumps(body).encode(), innertube._HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # fixed https youtube.com URL
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, None


def walk(node, counts: dict[str, int]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if any(word.lower() in key.lower() for word in INTEREST):
                counts[key] = counts.get(key, 0) + 1
            walk(value, counts)
    elif isinstance(node, list):
        for value in node:
            walk(value, counts)


def run(out: Path, label: str, endpoint: str, payload: dict) -> None:
    status, data = post(endpoint, payload)
    size = len(json.dumps(data)) if data else 0
    print(f"\n[{label}] {endpoint} {payload}  HTTP {status}  {size} bytes")
    if status == 429 or status in (403,) or status >= 500:
        raise Blocked(f"{label}: HTTP {status}")
    if data is None:
        return
    (out / f"{label}.json").write_text(json.dumps(data, indent=1))
    counts: dict[str, int] = {}
    walk(data, counts)
    print("  top-level keys:", list(data)[:12])
    for key, n in sorted(counts.items()):
        print(f"  {key}: {n}")
    time.sleep(PAUSE_S)


def discover(query: str, prefix: str = "") -> str:
    found = [e for e in innertube.search(query, count=20, kind="playlist") if str(e.get("id", "")).startswith(prefix)]
    time.sleep(PAUSE_S)
    return found[0]["id"] if found else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--playlist", default="")
    ap.add_argument("--topic", default="")
    ap.add_argument("--private", default="")
    ap.add_argument("--mix-video", default="dQw4w9WgXcQ")
    args = ap.parse_args()
    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        print("OUT_DIR must be new or empty", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    try:
        playlist = args.playlist or discover("lofi hip hop playlist")
        topic = args.topic or discover("Future Nostalgia Dua Lipa album", "OLAK")
        print("playlist:", playlist or "none found", "| topic:", topic or "none found")
        probes = [("mix-browse", "browse", {"browseId": "VLRD" + args.mix_video}),
                  ("mix-next", "next", {"videoId": args.mix_video, "playlistId": "RD" + args.mix_video}),
                  ("watch-later", "browse", {"browseId": "VLWL"})]
        if playlist:
            probes.insert(0, ("playlist", "browse", {"browseId": "VL" + playlist}))
        if topic:
            probes.insert(1, ("topic", "browse", {"browseId": "VL" + topic}))
        if args.private:
            probes.append(("private", "browse", {"browseId": "VL" + args.private}))
        for probe in probes:
            run(out, *probe)
    except Blocked as exc:
        print(f"\nSTOPPED at the first block, no retry: {exc}", file=sys.stderr)
        return 1
    print(f"\nSaved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
