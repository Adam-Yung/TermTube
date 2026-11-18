from src import channel_bookmarks

A = "UCuAXFkgsw1L7xaCfnd5JJOw"
B = "UC_x5XG1OV2P6uZZ5FSM9Ttw"


def followed(channel_id):
    return any(e["id"] == channel_id for e in channel_bookmarks.entries())

def test_toggle_round_trip(temp_channels):
    assert channel_bookmarks.entries() == [] and not followed(A)
    assert channel_bookmarks.toggle(A, "Rick", "https://yt3/a.jpg") is True
    assert followed(A)
    assert channel_bookmarks.toggle(A, "Rick") is False
    assert not followed(A) and channel_bookmarks.entries() == []


def test_entries_are_channel_rows_newest_first_and_survive_a_reload(temp_channels, monkeypatch):
    times = iter([100.0, 200.0])
    monkeypatch.setattr("src.channel_bookmarks.time.time", lambda: next(times))
    channel_bookmarks.toggle(A, "Rick", "https://yt3/a.jpg")
    channel_bookmarks.toggle(B, "Google")
    channel_bookmarks._store.flush()
    channel_bookmarks._store._data = None
    rows = channel_bookmarks.entries()
    assert [r["id"] for r in rows] == [B, A]
    assert rows[1]["title"] == "Rick" and rows[1]["thumbnail"] == "https://yt3/a.jpg"
    assert rows[1]["_is_channel"] and rows[1]["channel_url"] == f"https://www.youtube.com/channel/{A}"


def test_a_value_that_is_not_a_channel_id_is_refused(temp_channels):
    assert channel_bookmarks.toggle("@handle", "x") is False and channel_bookmarks.entries() == []


def test_a_corrupt_file_reads_as_empty_and_following_still_works(temp_channels):
    temp_channels.write_text("{not json", encoding="utf-8")
    channel_bookmarks._store._data = None
    assert channel_bookmarks.entries() == []
    assert channel_bookmarks.toggle(A, "Rick") is True
    assert [r["id"] for r in channel_bookmarks.entries()] == [A]


def test_a_second_follow_of_one_id_never_duplicates(temp_channels):
    channel_bookmarks.toggle(A, "Rick")
    channel_bookmarks.toggle(A, "Rick")
    channel_bookmarks.toggle(A, "Rick")
    assert len(channel_bookmarks.entries()) == 1
