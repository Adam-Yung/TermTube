"""One InnerTube list item (video, Short, channel, playlist row) as a TermTube entry, and the text parsing it needs."""

from __future__ import annotations

import re
from collections.abc import Iterator

from src.entries import ChannelEntry, Entry, PlaylistEntry, VideoEntry


def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _last_url(images: list[dict]) -> str:
    """The URL of the last, largest image of a size list; empty when there is none."""
    return images[-1].get("url", "") if images else ""


def _link_channel(entry: dict, channel_id: str) -> None:
    """Add the channel id and URL to a row, only for a real ``UC…`` id."""
    if channel_id.startswith("UC"):
        entry["channel_id"] = channel_id
        entry["channel_url"] = f"https://www.youtube.com/channel/{channel_id}"


def _byline(runs: list[dict]) -> tuple[str, str]:
    """(name, browse id) from the first run of a byline text."""
    first = (runs or [{}])[0]
    return first.get("text", ""), first.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")


_MULTIPLIERS = {"K": 1000, "M": 1_000_000, "B": 1_000_000_000}


VIDEO_COUNT = re.compile(r"^[\d,]+ videos?$")


_SUBSCRIBERS_WORD = re.compile(r"subscribers?", re.IGNORECASE)


def text_of(node: dict | None) -> str:
    """Plain text of an InnerTube text node (``simpleText`` or ``runs``)."""
    if not node:
        return ""
    return node.get("simpleText") or "".join(r.get("text", "") for r in node.get("runs", []))


def _runs_text(node: dict | None) -> str:
    runs = (node or {}).get("runs") or []
    return "".join(r.get("text", "") for r in runs) or (node or {}).get("simpleText", "")


def parse_view_count(text: str) -> int | None:
    """Parse view count from text like '105K views' or '1.2M views'."""
    if not text:
        return None
    match = re.search(r"([\d,.]+)\s*([KMB]?)", text)
    if not match:
        return None
    try:
        num = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(num * _MULTIPLIERS.get(match.group(2), 1))


def parse_duration_text(text: str) -> int | None:
    """Parse duration from text like '3:45' or '1:02:30' to seconds."""
    if not text:
        return None
    parts = text.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:
            return int(parts[0])
    except ValueError:
        pass
    return None


def parse_int(value) -> int | None:
    """Safely parse a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def find_text(node, pattern: re.Pattern) -> str:
    """First string anywhere under ``node`` that matches ``pattern``."""
    if isinstance(node, str):
        return node if pattern.search(node) else ""
    children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
    for child in children:
        found = find_text(child, pattern)
        if found:
            return found
    return ""


def _https(url: str) -> str:
    return "https:" + url if url.startswith("//") else url


def _lockup_details(lvm: dict) -> dict:
    return lvm.get("metadata", {}).get("lockupMetadataViewModel", {})


def _lockup_rows(meta: dict) -> list[dict]:
    return meta.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])


def _view_and_age_texts(meta: dict) -> tuple[str, str]:
    """(view count text, published text) from the metadata rows under a lockup's title."""
    view_count_text = ""
    published_text = ""
    for row in _lockup_rows(meta):
        for part in row.get("metadataParts", []):
            text = part.get("text", {}).get("content", "")
            if "view" in text.lower() or "watching" in text.lower():
                view_count_text = text
            elif "ago" in text.lower() or "streamed" in text.lower():
                published_text = text
    return view_count_text, published_text


def _badge_texts(lvm: dict) -> Iterator[str]:
    """Texts of the badges drawn over a lockup's thumbnail."""
    overlays = lvm.get("contentImage", {}).get("thumbnailViewModel", {}).get("overlays", [])
    for overlay in overlays:
        bottom = overlay.get("thumbnailBottomOverlayViewModel", {})
        for badge in bottom.get("badges", []) if bottom else []:
            yield badge.get("thumbnailBadgeViewModel", {}).get("text", "")


def _duration_and_live(lvm: dict) -> tuple[str, bool]:
    """(duration text, is live): badges are read up to the first duration."""
    is_live = False
    for text in _badge_texts(lvm):
        if text.upper() == "LIVE":
            is_live = True
        elif text and ":" in text:
            return text, is_live
    return "", is_live


def video_from_lockup(lvm: dict) -> VideoEntry | None:
    """A video entry from a ``lockupViewModel`` (channel grids and playlist pages share it), or None without an id."""
    if not lvm:
        return None

    video_id = lvm.get("contentId", "")
    if not video_id:
        return None

    meta = _lockup_details(lvm)
    view_count_text, published_text = _view_and_age_texts(meta)
    duration_text, is_live = _duration_and_live(lvm)
    sources = lvm.get("contentImage", {}).get("thumbnailViewModel", {}).get("image", {}).get("sources", [])

    entry: VideoEntry = {
        "id": video_id,
        "title": meta.get("title", {}).get("content", ""),
        "view_count_text": view_count_text,
        "published_text": published_text,
        "duration_text": duration_text,
        "view_count": parse_view_count(view_count_text),
        "duration": parse_duration_text(duration_text),
        "thumbnail": _last_url(sources),
        "webpage_url": _watch_url(video_id),
        "_type": "url",
    }
    if is_live:
        entry["is_live"] = True
    return entry


def channel_video(item: dict) -> VideoEntry | None:
    """One /browse richGridRenderer item as a video entry, or None if it is not a video."""
    ri = item.get("richItemRenderer", {})
    if not ri:
        return None
    return video_from_lockup(ri.get("content", {}).get("lockupViewModel", {}))


def short_video(item: dict) -> VideoEntry | None:
    """One Shorts-tab ``shortsLockupViewModel`` item as a video entry. [verify live]"""
    vm = item.get("richItemRenderer", {}).get("content", {}).get("shortsLockupViewModel", {})
    command = vm.get("onTap", {}).get("innertubeCommand", {})
    video_id = command.get("reelWatchEndpoint", {}).get("videoId") or vm.get("entityId", "").removeprefix(
        "shorts-shelf-item-"
    )
    if not video_id:
        return None
    meta = vm.get("overlayMetadata", {})
    views_text = meta.get("secondaryText", {}).get("content", "")
    sources = vm.get("thumbnail", {}).get("sources", [])
    return {
        "id": video_id,
        "title": meta.get("primaryText", {}).get("content", ""),
        "view_count_text": views_text,
        "view_count": parse_view_count(views_text),
        "thumbnail": _last_url(sources),
        "webpage_url": _watch_url(video_id),
        "_type": "url",
    }


def panel_video(pr: dict) -> VideoEntry | None:
    """One ``playlistPanelVideoRenderer`` (a row of a Mix) as a video entry."""
    video_id = pr.get("videoId", "")
    if not video_id:
        return None
    name, channel_id = _byline((pr.get("longBylineText") or pr.get("shortBylineText") or {}).get("runs"))
    entry: VideoEntry = {
        "id": video_id,
        "title": text_of(pr.get("title")) or video_id,
        "uploader": name,
        "channel": name,
        "duration": parse_duration_text(text_of(pr.get("lengthText"))),
        "thumbnail": _last_url(pr.get("thumbnail", {}).get("thumbnails") or []),
        "webpage_url": _watch_url(video_id),
        "_type": "url",
    }
    _link_channel(entry, channel_id)
    return entry


def _name_from_lockup(entry: VideoEntry, lvm: dict) -> None:
    """On a playlist page the uploader, with the channel link, is the first metadata part."""
    rows = _lockup_rows(_lockup_details(lvm))
    part = next((p.get("text", {}) for r in rows for p in r.get("metadataParts", []) if p.get("text")), {})
    if not part.get("content"):
        return
    entry["uploader"] = entry["channel"] = part["content"]
    taps = (run.get("onTap", {}).get("innertubeCommand", {}) for run in part.get("commandRuns", []))
    _link_channel(entry, next((tap.get("browseEndpoint", {}).get("browseId", "") for tap in taps), ""))


def playlist_video(item: dict) -> VideoEntry | None:
    """One ``playlistVideoRenderer`` of a playlist page as a video entry. [verify live]"""
    lvm = item.get("lockupViewModel")
    if lvm:  # the layout YouTube serves now
        if lvm.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
            return None
        entry = video_from_lockup(lvm)
        if entry:
            _name_from_lockup(entry, lvm)
        return entry
    pv = item.get("playlistVideoRenderer") or {}
    video_id = pv.get("videoId", "")
    if not video_id:
        return None
    name, channel_id = _byline((pv.get("shortBylineText") or {}).get("runs"))
    entry: VideoEntry = {
        "id": video_id,
        "title": _runs_text(pv.get("title")) or video_id,
        "uploader": name,
        "channel": name,
        "duration": parse_int(pv.get("lengthSeconds")),
        "thumbnail": _last_url(pv.get("thumbnail", {}).get("thumbnails") or []),
        "webpage_url": _watch_url(video_id),
        "_type": "url",
    }
    _link_channel(entry, channel_id)
    return entry


def _parse_search_video(vr: dict) -> VideoEntry | None:
    video_id = vr.get("videoId")
    if not video_id:
        return None
    owner = vr.get("ownerText") or vr.get("longBylineText") or {}
    browse = ((owner.get("runs") or [{}])[0].get("navigationEndpoint") or {}).get("browseEndpoint") or {}
    thumbs = (vr.get("thumbnail") or {}).get("thumbnails") or []
    badges = {b.get("metadataBadgeRenderer", {}).get("style", "") for b in vr.get("badges") or []}
    name = text_of(owner)
    channel_id = browse.get("browseId", "")
    return {
        "id": video_id,
        "title": text_of(vr.get("title")),
        "uploader": name,
        "channel": name,
        "channel_id": channel_id,
        "channel_url": f"https://www.youtube.com/channel/{channel_id}" if channel_id else "",
        "duration": parse_duration_text(text_of(vr.get("lengthText"))),
        "view_count": parse_view_count(text_of(vr.get("viewCountText"))),
        "published_text": text_of(vr.get("publishedTimeText")),
        "thumbnail": _last_url(thumbs),
        "is_live": "BADGE_STYLE_TYPE_LIVE_NOW" in badges,
        "webpage_url": _watch_url(video_id),
        "_type": "url",
    }


def _parse_search_channel(cr: dict) -> ChannelEntry | None:
    channel_id = cr.get("channelId")
    if not channel_id:
        return None
    name = text_of(cr.get("title"))
    thumbs = (cr.get("thumbnail") or {}).get("thumbnails") or []
    handle = ((cr.get("navigationEndpoint") or {}).get("browseEndpoint") or {}).get("canonicalBaseUrl", "")
    url = f"https://www.youtube.com{handle}" if handle.startswith("/") else f"https://www.youtube.com/channel/{channel_id}"
    # The subscriber count sits in one of two fields depending on the page version; the other holds the @handle.
    texts = [text_of(cr.get("subscriberCountText")), text_of(cr.get("videoCountText"))]
    subs = next((t for t in texts if _SUBSCRIBERS_WORD.search(t)), "")
    return {
        "id": channel_id, "title": name, "channel": name, "channel_id": channel_id, "channel_url": url,
        "uploader": name, "uploader_url": url, "subscriber_count": parse_view_count(subs),
        "thumbnail": _https(_last_url(thumbs)),
        "description": text_of(cr.get("descriptionSnippet")), "_is_channel": True,
    }


def _parse_search_playlist(pr: dict) -> PlaylistEntry | None:
    playlist_id = pr.get("playlistId")
    if not playlist_id:
        return None
    title = text_of(pr.get("title")) or playlist_id
    thumbs = ((pr.get("thumbnails") or [{}])[0].get("thumbnails")) or []
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    return {
        "id": playlist_id, "title": title, "url": url, "webpage_url": url,
        "uploader": text_of(pr.get("shortBylineText")), "thumbnail": _https(_last_url(thumbs)),
        "playlist_count": parse_view_count(str(pr.get("videoCount", ""))),
        "_type": "playlist", "_is_playlist": True, "_playlist_name": title,
    }


def playlist_item(item: dict) -> PlaylistEntry | None:
    """One ``lockupViewModel`` grid item as a playlist entry, or None for any other content type."""
    lvm = item.get("lockupViewModel") or {}
    playlist_id = lvm.get("contentId", "")
    if lvm.get("contentType") != "LOCKUP_CONTENT_TYPE_PLAYLIST" or not playlist_id:
        return None
    title = lvm.get("metadata", {}).get("lockupMetadataViewModel", {}).get("title", {}).get("content", "")
    thumb = lvm.get("contentImage", {}).get("collectionThumbnailViewModel", {}).get("primaryThumbnail", {})
    thumb = thumb.get("thumbnailViewModel", {})
    sources = thumb.get("image", {}).get("sources") or []
    count_text = find_text(thumb.get("overlays", []), VIDEO_COUNT)
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    return {
        "id": playlist_id,
        "title": title or playlist_id,
        "url": url,
        "webpage_url": url,
        "thumbnail": _last_url(sources),
        "playlist_count": parse_view_count(count_text),
        "_type": "playlist",
        "_is_playlist": True,
        "_playlist_name": title or playlist_id,
    }


def search_item(item: dict) -> Entry | None:
    """One search row (video, channel or playlist) as an entry; None for shelves, ads and anything else."""
    if "videoRenderer" in item:
        return _parse_search_video(item["videoRenderer"])
    if "channelRenderer" in item:
        return _parse_search_channel(item["channelRenderer"])
    if "playlistRenderer" in item:
        return _parse_search_playlist(item["playlistRenderer"])
    return playlist_item(item)
