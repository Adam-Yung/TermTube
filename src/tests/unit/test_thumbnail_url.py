from src.ui.thumbnail import best_thumb_url


def test_extractor_thumbnail_wins():
    assert best_thumb_url({"id": "dQw4w9WgXcQ", "thumbnail": "https://x/y.jpg"}) == "https://x/y.jpg"


def test_prefers_last_jpg_of_thumbnails():
    entry = {"id": "dQw4w9WgXcQ", "thumbnails": [{"url": "a.webp"}, {"url": "b.jpg"}, {"url": "c.jpg"}]}
    assert best_thumb_url(entry) == "c.jpg"


def test_derived_from_video_id_when_entry_has_none():
    assert best_thumb_url({"id": "dQw4w9WgXcQ"}) == "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"


def test_no_url_for_non_video_rows():
    assert best_thumb_url({"id": "__playlist__mix"}) == ""
    assert best_thumb_url({"id": "UCuAXFkgsw1L7xaCfnd5JJOw", "_is_channel": True}) == ""
    assert best_thumb_url({}) == ""
