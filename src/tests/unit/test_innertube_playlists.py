"""InnerTube playlist and Mix pages, parsed from responses recorded from youtube.com."""

import json
from functools import partial
from pathlib import Path
from unittest.mock import patch

from src import innertube

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_playlist_page_parses_videos_with_their_channel_and_returns_the_token():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_videos.json")) as post:
        page = innertube.fetch_playlist_page("PLabc")
    assert post.call_args.args[1]["browseId"] == "VLPLabc"
    first, second = page.entries
    assert page.token == "PL-TOKEN"
    assert first["id"] == "PPPPPPPPPPP" and first["title"] == "First track" and first["duration"] == 245
    assert first["uploader"] == "Other Channel" and first["channel_id"] == "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    assert first["channel_url"].endswith(first["channel_id"]) and first["thumbnail"].endswith("hq.jpg")
    assert second["id"] == "QQQQQQQQQQQ" and "channel_id" not in second


def test_playlist_continuation_sends_only_the_token_and_failure_is_empty():
    more = load("innertube_channel_videos_more.json")
    with patch.object(innertube, "_post_json", return_value=more) as post:
        innertube.fetch_playlist_page("PLabc", "TOK")
    assert post.call_args.args[1]["continuation"] == "TOK" and "browseId" not in post.call_args.args[1]
    with patch.object(innertube, "_post_json", return_value=None):
        assert innertube.fetch_playlist_page("PLabc") == innertube.ChannelPage([])


def test_playlist_page_parses_the_lockup_layout_recorded_from_youtube():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_videos_lockup.json")):
        page = innertube.fetch_playlist_page("PLRPUpQa70I6A")
    first, second = page.entries
    assert first["id"] == "cv8tEbKtEvk" and first["title"].endswith("Gemini Live") and first["duration"] == 126
    assert first["uploader"] == "Google for Developers" and first["channel_id"] == "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    assert second["id"] == "ID6vEy94j7c"
    assert page.token.startswith("4qmFsgIx")


def test_playlist_first_page_carries_the_header_recorded_from_youtube():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_page_header.json")):
        page = innertube.fetch_playlist_page("PLBTanuC8SLeZUH4mYXFvRbDfxTMKvNLHJ")
    info = page.info
    assert info["title"].startswith("Lofi Music 2027") and info["description"].startswith("Lofi Music 2027")
    assert (info["owner"], info["owner_id"]) == ("Hitsify", "UCnFrtWHPWzuvzMwwJLv9dnA")
    assert (info["video_count"], info["view_count"], info["updated"]) == (50, 62909, "Updated 4 days ago")
    assert info["thumbnail"].startswith("https://i.ytimg.com/vi/GgVcgbtHY9k/")
    assert info["playlist_id"] == "PLBTanuC8SLeZUH4mYXFvRbDfxTMKvNLHJ" and len(page.entries) == 2


def test_a_continuation_page_has_no_header():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_videos_lockup.json")):
        assert innertube.fetch_playlist_page("PLx", "tok").info is None


def test_an_unviewable_playlist_reports_youtubes_own_reason():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_unviewable.json")):
        page = innertube.fetch_playlist_page("RDdQw4w9WgXcQ")
    assert page.entries == []
    assert page.info == {"playlist_id": "RDdQw4w9WgXcQ", "unavailable": "This playlist type is unviewable."}


def _record_request(sent, url, payload, **_):
    """Notes (endpoint, playlist id, video id) of each request and answers with the recorded Mix."""
    sent.append((url.rsplit("/", 1)[-1].split("?")[0], payload.get("playlistId"), payload.get("videoId")))
    return load("innertube_mix_next.json")


def test_a_mix_loads_through_next_with_the_playlist_id_alone():
    sent = []
    with patch.object(innertube, "_post_json", partial(_record_request, sent)):
        page = innertube.fetch_mix_page("RDdQw4w9WgXcQ")
    assert sent == [("next", "RDdQw4w9WgXcQ", None)]
    first = page.entries[0]
    assert first["id"] == "dQw4w9WgXcQ" and first["duration"] == 214 and first["channel_id"].startswith("UC")
    assert first["uploader"] == "Rick Astley" and first["thumbnail"].startswith("https://")
    assert page.info["title"].startswith("Mix - Rick Astley") and page.info["owner"] == "YouTube"
    assert page.info["video_count"] is None and page.info["mix"] is True and len(page.entries) == 3


def test_a_mix_continues_from_its_last_video_and_stays_endless():
    with patch.object(innertube, "_post_json", return_value=load("innertube_mix_next.json")):
        page = innertube.fetch_mix_page("RDdQw4w9WgXcQ")
    with patch.object(innertube, "_post_json", return_value=load("innertube_mix_next.json")) as post:
        more = innertube.fetch_mix_page("RDdQw4w9WgXcQ", page.token)
    sent = [c.args[1] for c in post.call_args_list]
    assert sent[0]["videoId"] == page.entries[-1]["id"] and sent[0]["playlistId"] == "RDdQw4w9WgXcQ"
    assert more.token and more.info is None


def test_a_mix_that_needs_an_account_reports_it():
    with patch.object(innertube, "_post_json", return_value={"contents": {}}):
        page = innertube.fetch_mix_page("RDMM")
    assert page.entries == [] and page.info["unavailable"] and page.info["playlist_id"] == "RDMM"
