#!/usr/bin/env python3
"""Find out why YouTube channel RSS fails on this network, and what TermTube does about it.

Anonymous, certificate-verified requests to youtube.com only (no cookies, no login, no media). About 30 small requests.
Usage: scripts/diagnose-rss.py   (paste the whole output back; it holds only response codes, headers and snippets)
"""
from __future__ import annotations

import os
import platform
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CHANNELS = {
    "Google Developers": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
    "Rick Astley": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "YouTube": "UCBR8-60-B28hp2BmDPdntcQ",
}
FEED = "https://www.youtube.com/feeds/videos.xml"
USER_AGENTS = {
    "python-urllib": None,
    "browser": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "curl": "curl/8.7.1",
    "feedreader": "Feedly/1.0 (+http://www.feedly.com/fetcher.html)",
}
SHOWN_HEADERS = ("content-type", "content-length", "server", "via", "x-cache", "cache-control", "location",
                 "retry-after")


class _Trace(urllib.request.HTTPRedirectHandler):
    """Follows redirects and remembers each hop."""

    def __init__(self) -> None:
        self.hops: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops.append(f"{code} -> {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def probe(url: str, user_agent: str | None = None, opener=None, timeout: int = 12) -> dict:
    """GET ``url``; a dict with status, headers, body snippet, redirect hops, timing and any error."""
    trace = _Trace()
    opener = opener or urllib.request.build_opener(trace)
    headers = {"User-Agent": user_agent} if user_agent else {}
    result: dict = {"url": url, "status": None, "headers": {}, "body": b"", "hops": trace.hops, "error": "", "ms": 0}
    start = time.perf_counter()
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            result["status"], result["headers"] = resp.status, dict(resp.headers.items())
            result["body"] = resp.read(4000)
    except urllib.error.HTTPError as exc:
        result["status"], result["headers"] = exc.code, dict(exc.headers.items())
        result["body"] = exc.read(4000)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["ms"] = round((time.perf_counter() - start) * 1000)
    return result


def describe(result: dict) -> str:
    """One report line for a probe result."""
    if result["error"]:
        return f"ERROR {result['error']} ({result['ms']} ms)"
    shown = {k.lower(): v for k, v in result["headers"].items() if k.lower() in SHOWN_HEADERS}
    text = re.sub(r"\s+", " ", result["body"].decode("utf-8", "replace")).strip()[:140]
    head = result["body"][:600]
    kind = "ATOM" if b"<feed" in head else ("HTML" if b"<html" in head.lower() else "other")
    hops = f" redirects={result['hops']}" if result["hops"] else ""
    headers = " ".join(f"{k}={v}" for k, v in shown.items() if k != "content-length")
    return f"{result['status']} {kind} {result['ms']} ms{hops} [{headers}] body: {text!r}"


def verdict(statuses: list[int | None]) -> str:
    working = [s for s in statuses if s == 200]
    if working and len(working) == len(statuses):
        return "RSS works for every probe."
    if working:
        return f"RSS works for {len(working)} of {len(statuses)} probes: see which form or user agent differs."
    if all(s == 404 for s in statuses):
        return "Every probe got 404: the endpoint is down or blocked for this network, not a URL mistake."
    return f"No probe returned 200 (statuses seen: {sorted({s for s in statuses}, key=str)})."


def section(title: str) -> None:
    print(f"\n== {title}")


def environment() -> None:
    section("Environment")
    print(f"python {platform.python_version()} on {platform.platform()}; {ssl.OPENSSL_VERSION}")
    proxies = [k for k in os.environ if k.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")]
    print("proxy variables set:", ", ".join(proxies) or "none")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo("www.youtube.com", 443, proto=socket.IPPROTO_TCP)}
        print(f"www.youtube.com resolves to {len(addresses)} address(es), e.g. {sorted(addresses)[0]}")
    except OSError as exc:
        print(f"DNS failed: {exc}")


def sanity() -> None:
    section("Sanity: is youtube.com reachable at all?")
    print("GET /               ", describe(probe("https://www.youtube.com/", USER_AGENTS["browser"])))
    print("GET /feeds/nope.xml  ", describe(probe("https://www.youtube.com/feeds/nope.xml", USER_AGENTS["browser"])))


def matrix() -> list[int | None]:
    section("RSS matrix: URL form x channel (browser user agent)")
    statuses: list[int | None] = []
    for name, cid in CHANNELS.items():
        forms = {
            "channel_id": f"{FEED}?channel_id={cid}",
            "playlist_id=UU (uploads)": f"{FEED}?playlist_id=UU{cid[2:]}",
            "playlist_id=UULF (videos only)": f"{FEED}?playlist_id=UULF{cid[2:]}",
            "http (not https)": f"http://www.youtube.com/feeds/videos.xml?channel_id={cid}",
            "no www": f"https://youtube.com/feeds/videos.xml?channel_id={cid}",
            "m.youtube.com": f"https://m.youtube.com/feeds/videos.xml?channel_id={cid}",
        }
        print(f"-- {name}")
        for label, url in forms.items():
            result = probe(url, USER_AGENTS["browser"])
            statuses.append(result["status"])
            print(f"   {label:32} {describe(result)}")
    return statuses


def user_agents() -> list[int | None]:
    section("RSS by user agent (Google Developers, channel_id form)")
    statuses: list[int | None] = []
    url = f"{FEED}?channel_id={CHANNELS['Google Developers']}"
    for label, agent in USER_AGENTS.items():
        result = probe(url, agent)
        statuses.append(result["status"])
        print(f"   {label:14} {describe(result)}")
    return statuses


def app_path() -> None:
    section("What TermTube does (src/feeds.py and InnerTube, anonymous)")
    from src import feeds, innertube

    cid = CHANNELS["Google Developers"]
    start = time.perf_counter()
    rss = feeds._fetch_rss(cid)
    print(f"feeds._fetch_rss: {len(rss)} entries in {round((time.perf_counter() - start) * 1000)} ms")
    start = time.perf_counter()
    latest = feeds.channel_latest(cid)
    ms = round((time.perf_counter() - start) * 1000)
    first = (latest[:1] or [{}])[0].get("title", "-")
    print(f"feeds.channel_latest: {len(latest)} entries in {ms} ms; first: {first!r}")
    timed = sum(1 for e in latest if e.get("duration"))
    print(f"  entries with a duration: {timed} of {len(latest)} (RSS gives none, InnerTube gives them)")
    print(f"  source: {'RSS' if rss else 'InnerTube fallback'}")
    start = time.perf_counter()
    browse = innertube.fetch_channel_videos(cid)
    print(f"innertube.fetch_channel_videos: {len(browse)} entries in {round((time.perf_counter() - start) * 1000)} ms")


def main() -> int:
    print(f"TermTube RSS diagnosis, {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    environment()
    sanity()
    statuses = matrix() + user_agents()
    section("Verdict")
    print(verdict(statuses))
    app_path()
    return 0


if __name__ == "__main__":
    sys.exit(main())
