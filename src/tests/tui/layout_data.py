"""Long, crowded fake rows for the layout audits."""

LONG = "A rather long video title that goes on and on to test how a list row copes with a narrow column"


def long_entries(count=40, **extra):
    return [
        {"id": f"vid{i:08d}", "title": f"{LONG} {i}", "uploader": "A Channel With A Long Name Indeed",
         "duration": 3700, "view_count": 1234567, "upload_date": "20250101", "description": "d " * 200, **extra}
        for i in range(count)
    ]


def long_channels(count=30):
    return [{"id": f"UC{i:020d}", "title": f"Channel number {i}", "channel": f"Channel number {i}", "_is_channel": True,
             "subscriber_count": 123456, "video_count": 321, "channel_url": f"https://www.youtube.com/channel/UC{i}"}
            for i in range(count)]
