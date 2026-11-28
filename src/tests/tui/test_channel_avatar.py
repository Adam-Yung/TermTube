"""A channel header with an avatar loads it."""
from src.tui.screens.channel_screen import ChannelScreen


async def test_a_header_with_an_avatar_asks_for_it(app, monkeypatch):
    asked = []
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_start_content_once", lambda self: None)
    monkeypatch.setattr(
        "src.tui.screens.mixins.channel_header.load_thumbnail",
        lambda _app, _panel, avatar_id, **kw: asked.append((avatar_id, kw["url"], kw["is_current"]())),
    )
    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen("https://www.youtube.com/channel/UCa", "A"))
        await pilot.pause()
        app.screen._apply_info({"channel": "A", "channel_id": "UCa", "thumbnail": "https://example.invalid/a.jpg"})
        await app.workers.wait_for_complete()
        assert asked == [("ch_UCa", "https://example.invalid/a.jpg", True)]
