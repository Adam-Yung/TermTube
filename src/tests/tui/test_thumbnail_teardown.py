"""A thumbnail worker finishing after its panel is gone must not raise (CI saw WorkerFailed from it)."""

from pathlib import Path


async def test_thumbnail_setters_are_no_ops_after_the_widget_is_removed(app):
    async with app.run_test(size=(100, 30)) as pilot:
        panel = app.screen.query_one("#detail-panel")
        await panel.query_one("#thumbnail").remove()
        await pilot.pause(0.1)
        panel.set_thumbnail_video_id("AAAAAAAAAAA")
        panel.set_thumbnail_loading()
        panel.set_thumbnail_placeholder()
        panel.set_thumbnail_image("AAAAAAAAAAA", Path("nowhere.jpg"))
        panel.set_thumbnail_ansi("AAAAAAAAAAA", "x")


async def test_the_setters_still_reach_the_widget_while_it_exists(app):
    async with app.run_test(size=(100, 30)) as pilot:
        panel = app.screen.query_one("#detail-panel")
        panel.set_thumbnail_video_id("AAAAAAAAAAA")
        await pilot.pause(0.1)
        assert panel._thumbnail() is not None
