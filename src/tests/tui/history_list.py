"""Reading the History tab's list, shared by the list-tool modules."""

from src.tui.widgets.video_list import VideoListItem, VideoListPanel


def panel_of(app) -> VideoListPanel:
    return app.screen.query_one("#video-list-panel", VideoListPanel)


def children(panel):
    return list(panel._lv.children)


def rows(panel):
    return [c for c in children(panel) if isinstance(c, VideoListItem)]


def cursor_id(panel):
    entry = panel.selected_entry
    return entry["id"] if entry else None


async def open_history(app, pilot):
    await pilot.pause(0.8)  # a running home load is not cancelled by a tab switch and would add rows here
    await pilot.press("f4")
    await pilot.pause(0.6)
