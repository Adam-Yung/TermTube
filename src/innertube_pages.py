"""Reads whole InnerTube replies: browse grids and tokens, playlist and channel headers, search sections, Mixes."""

from __future__ import annotations

import json
import re

from src import logger
from src.entries import Entry
from src.innertube_rows import (
    VIDEO_COUNT,
    find_text,
    panel_video,
    parse_int,
    parse_view_count,
    search_item,
    text_of,
)
from src.strings import text

CHANNEL_TABS = ("videos", "shorts", "live", "playlists")
_VIDEO_COUNT_TEXT = re.compile(r"^[\d,.]+\s+videos?$")
_VIEW_COUNT_TEXT = re.compile(r"^[\d,.]+\s+views?$")
_SUBSCRIBERS = re.compile(r"^[\d.,]+\s*[KMB]?\s+subscribers?$", re.IGNORECASE)
_JOINED = re.compile(r"^Joined\b", re.IGNORECASE)


def _upload_date(microformat: dict) -> str | None:
    """yt-dlp convention: YYYYMMDD."""
    date = microformat.get("uploadDate") or microformat.get("publishDate")
    if date and "T" in date:
        date = date.split("T")[0]
    return date.replace("-", "") if date else date


def video_details(data: dict, video_id: str) -> dict | None:
    """A /player reply shaped like a yt-dlp info dict (``_innertube`` is set), or None without ``videoDetails``."""
    vd = data.get("videoDetails")
    if not vd:
        logger.debug("innertube: no videoDetails for %s (keys: %s)",
                     video_id, list(data.keys())[:5])
        return None

    mf = data.get("microformat", {}).get("playerMicroformatRenderer", {})
    owner_url = mf.get("ownerProfileUrl", "")
    uploader_id = ""
    if "/@" in owner_url:
        uploader_id = "@" + owner_url.split("/@", 1)[1].rstrip("/")

    return {
        "id": video_id,
        "title": vd.get("title", ""),
        "description": vd.get("shortDescription", ""),
        "view_count": parse_int(vd.get("viewCount")),
        "like_count": parse_int(mf.get("likeCount")),
        "upload_date": _upload_date(mf),
        "channel": vd.get("author", ""),
        "channel_id": vd.get("channelId", ""),
        "channel_url": f"https://www.youtube.com/channel/{vd.get('channelId', '')}",
        "uploader": vd.get("author", ""),
        "uploader_id": uploader_id,
        "uploader_url": owner_url.replace("http://", "https://") if owner_url else "",
        "duration": parse_int(vd.get("lengthSeconds")),
        "categories": [mf.get("category", "")] if mf.get("category") else [],
        "is_live": vd.get("isLiveContent", False),
        "keywords": vd.get("keywords", []),
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "_innertube": True,
    }


def _playlist_owner(parts: list[dict]) -> tuple[str, str]:
    """(name, channel id) from the "by Name" avatar-stack part of the header; empty strings when it is missing."""
    stack = next((p["avatarStack"]["avatarStackViewModel"]["text"] for p in parts if "avatarStack" in p), {})
    commands = [run.get("onTap", {}).get("innertubeCommand", {}) for run in stack.get("commandRuns") or []]
    ids = [c.get("browseEndpoint", {}).get("browseId", "") for c in commands]
    owner_id = next((i for i in ids if i), "")
    return stack.get("content", "").removeprefix("by ").strip(), owner_id


def _playlist_updated(data: dict) -> str:
    """"Updated 4 days ago": only the sidebar carries it."""
    items = ((data.get("sidebar") or {}).get("playlistSidebarRenderer") or {}).get("items") or []
    stats = [text_of(s) for i in items for s in (i.get("playlistSidebarPrimaryInfoRenderer") or {}).get("stats") or []]
    return next((t for t in stats if t.startswith("Updated")), "")


def playlist_info(data: dict, playlist_id: str) -> dict:
    """Header of a playlist's first /browse reply, or ``{"unavailable": <YouTube's reason>}`` when it carries an alert.

    Title, description and thumbnail come from the metadata and microformat blocks; the owner and the count rows from
    ``pageHeaderViewModel``. Every field is optional: a missing piece is an empty string or None, never an error.
    """
    info: dict = {"playlist_id": playlist_id}
    alerts = [text_of((a.get("alertRenderer") or {}).get("text")) for a in data.get("alerts") or []]
    if alerts and not data.get("header"):
        info["unavailable"] = next((a for a in alerts if a), "unavailable")
        return info
    meta = (data.get("metadata") or {}).get("playlistMetadataRenderer") or {}
    content = ((data.get("header") or {}).get("pageHeaderRenderer") or {}).get("content") or {}
    view_meta = content.get("pageHeaderViewModel", {}).get("metadata", {}).get("contentMetadataViewModel") or {}
    parts = [p for row in view_meta.get("metadataRows") or [] for p in row.get("metadataParts") or []]
    texts = [(p.get("text") or {}).get("content", "") for p in parts]
    owner, owner_id = _playlist_owner(parts)
    microformat = (data.get("microformat") or {}).get("microformatDataRenderer") or {}
    thumbs = microformat.get("thumbnail", {}).get("thumbnails") or []
    info.update(
        title=meta.get("title", ""),
        description=meta.get("description", ""),
        owner=owner,
        owner_id=owner_id,
        video_count=parse_view_count(next((t for t in texts if _VIDEO_COUNT_TEXT.match(t)), "")),
        view_count=parse_view_count(next((t for t in texts if _VIEW_COUNT_TEXT.match(t)), "")),
        updated=_playlist_updated(data),
        thumbnail=thumbs[-1].get("url", "") if thumbs else "",
    )
    return info


def browse_items(data: dict) -> list[dict]:
    """The grid items of a first /browse response (rich grid or playlist grid) or of a continuation response."""
    actions = data.get("onResponseReceivedActions")
    if actions:
        return actions[0].get("appendContinuationItemsAction", {}).get("continuationItems", [])
    tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
    selected = next((t["tabRenderer"] for t in tabs if t.get("tabRenderer", {}).get("selected")), {})
    content = selected.get("content", {})
    if "richGridRenderer" in content:
        return content["richGridRenderer"].get("contents", [])
    sections = content.get("sectionListRenderer", {}).get("contents", [])
    rows = [c for s in sections for c in s.get("itemSectionRenderer", {}).get("contents", [])]
    for row in rows:
        if "playlistVideoListRenderer" in row:
            return row["playlistVideoListRenderer"].get("contents", [])
    if any("lockupViewModel" in row for row in rows):  # a playlist page: videos, with the token in the section list
        return rows + [c for c in sections if "continuationItemViewModel" in c]
    return [i for c in rows for i in c.get("gridRenderer", {}).get("items", [])]


def next_token(items: list[dict]) -> str:
    for item in items:
        if "continuationItemRenderer" in item:
            command = item["continuationItemRenderer"].get("continuationEndpoint", {})
            return command.get("continuationCommand", {}).get("token", "")
        if "continuationItemViewModel" in item:
            command = item["continuationItemViewModel"].get("continuationCommand", {}).get("innertubeCommand", {})
            return command.get("continuationCommand", {}).get("token", "")
    return ""


def mix_page(data: dict | None, playlist_id: str, first: bool) -> tuple[list, str, dict | None]:
    """(entries, next token, header) of a /next reply for a Mix; the header only on the first page."""
    watch = (data or {}).get("contents", {}).get("twoColumnWatchNextResults", {})
    box = watch.get("playlist", {}).get("playlist") or {}
    items = [i["playlistPanelVideoRenderer"] for i in box.get("contents") or [] if "playlistPanelVideoRenderer" in i]
    entries = [e for e in map(panel_video, items) if e]
    if not entries:
        info = {"playlist_id": playlist_id, "unavailable": text("channel_screen.mix_unavailable")} if first else None
        return [], "", info
    endpoint = items[-1].get("navigationEndpoint", {}).get("watchEndpoint", {})
    token = json.dumps({k: endpoint[k] for k in ("videoId", "playlistId", "index", "params") if k in endpoint})
    info = {
        "playlist_id": playlist_id, "title": box.get("title", ""), "owner": text_of(box.get("ownerName")),
        "owner_id": "", "description": "", "video_count": None, "view_count": None, "updated": "", "mix": True,
        "thumbnail": entries[0]["thumbnail"],
    } if first else None
    return entries, token, info


def search_sections(data: dict) -> list[dict]:
    """The result sections of a first /search reply or of a continuation reply."""
    if "contents" in data:
        return (data["contents"].get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", []))
    actions = data.get("onResponseReceivedCommands") or [{}]
    return actions[0].get("appendContinuationItemsAction", {}).get("continuationItems", [])


def search_items(sections: list[dict]) -> tuple[list[Entry], str]:
    """Result entries and the next continuation token from a list of result sections."""
    entries: list[Entry] = []
    token = ""
    for section in sections:
        for item in section.get("itemSectionRenderer", {}).get("contents", []):
            entry = search_item(item)
            if entry:
                entries.append(entry)
        cont = section.get("continuationItemRenderer", {})
        token = cont.get("continuationEndpoint", {}).get("continuationCommand", {}).get("token", token)
    return entries, token


def _channel_tabs(data: dict) -> list[str]:
    """Which of ``CHANNEL_TABS`` the channel has, from the tab titles of the first /browse response."""
    tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
    titles = {t.get("tabRenderer", {}).get("title", "").lower() for t in tabs}
    return [tab for tab in CHANNEL_TABS if tab in titles]


def channel_info(data: dict | None, channel_id: str) -> dict | None:
    """Name, description, counts, avatar and tabs from a channel's first /browse reply, or None without metadata."""
    meta = ((data or {}).get("metadata") or {}).get("channelMetadataRenderer")
    if not meta:
        return None
    avatars = (meta.get("avatar") or {}).get("thumbnails") or []
    header = data.get("header", {})
    return {
        "channel_url": f"https://www.youtube.com/channel/{channel_id}",
        "channel": meta.get("title", ""),
        "channel_id": channel_id,
        "description": meta.get("description", ""),
        "subscriber_count": parse_view_count(find_text(header, _SUBSCRIBERS)),
        "thumbnail": avatars[-1].get("url", "") if avatars else "",
        "uploader_url": (meta.get("vanityChannelUrl") or "").replace("http://", "https://"),
        "video_count": parse_view_count(find_text(header, VIDEO_COUNT)),
        "joined": find_text(header, _JOINED),
        "tabs": _channel_tabs(data),
    }
