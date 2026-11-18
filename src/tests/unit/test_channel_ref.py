import pytest

from src import channel_ref

ID = "UCuAXFkgsw1L7xaCfnd5JJOw"


@pytest.mark.parametrize(
    "url, expected",
    [
        (f"https://www.youtube.com/channel/{ID}", ("id", ID)),
        (f"https://www.youtube.com/channel/{ID}/videos?view=0", ("id", ID)),
        (f"https://m.youtube.com/channel/{ID}/", ("id", ID)),
        ("https://www.youtube.com/@RickAstleyYT", ("handle", "@RickAstleyYT")),
        ("https://www.youtube.com/@RickAstleyYT/playlists", ("handle", "@RickAstleyYT")),
        ("https://www.youtube.com/c/Rick", ("c", "Rick")),
        ("https://www.youtube.com/user/rickastley/videos", ("user", "rickastley")),
        ("  https://www.youtube.com/@x  ", ("handle", "@x")),
    ],
)
def test_parse_each_url_form(url, expected):
    assert channel_ref.parse(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "", "https://www.youtube.com/", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/channel/UCshort", "https://www.youtube.com/playlist?list=PLx",
        "https://www.youtube.com/channelx/" + ID,
    ],
)
def test_parse_rejects_what_is_not_a_channel(url):
    assert channel_ref.parse(url) is None


def test_channel_id_only_for_the_id_form():
    assert channel_ref.channel_id(f"https://www.youtube.com/channel/{ID}/videos") == ID
    assert channel_ref.channel_id("https://www.youtube.com/@RickAstleyYT") is None
    assert channel_ref.channel_id("not a url") is None


def test_is_channel_id():
    assert channel_ref.is_channel_id(ID)
    assert not channel_ref.is_channel_id("UCx") and not channel_ref.is_channel_id("")
