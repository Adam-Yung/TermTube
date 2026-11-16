"""Notifications use the app's dialog palette and the theme accent, not Textual's default slab."""

import pytest
from textual.widgets._toast import Toast

ACCENT = {"crimson": "#ff4444", "amber": "#e8820c", "ocean": "#0ea5e9", "midnight": "#a855f7"}


def hex_of(color) -> str:
    return color.hex.lower()[:7]


async def shown_toasts(app, pilot, **kwargs):
    app.notify("info text", **kwargs)
    app.notify("warn text", severity="warning", **kwargs)
    app.notify("error text", severity="error", **kwargs)
    await pilot.pause(0.5)
    return {t._notification.severity: t for t in app.screen.query(Toast)}


@pytest.mark.parametrize("theme", sorted(ACCENT))
async def test_toast_colours_follow_the_theme(app, theme):
    app.config._data["theme"] = theme
    async with app.run_test(size=(100, 30), notifications=True) as pilot:
        for other in ACCENT:
            app.set_class(other == theme and other != "crimson", f"theme-{other}")
        toasts = await shown_toasts(app, pilot, timeout=30)
    info, warning, error = toasts["information"], toasts["warning"], toasts["error"]
    assert hex_of(info.styles.background) == "#141414"
    assert hex_of(info.styles.border_left[1]) == ACCENT[theme]
    assert hex_of(warning.styles.border_left[1]) == "#ddc800"
    assert hex_of(error.styles.border_top[1]) == "#ff4444"


async def test_toasts_sit_below_the_tab_bar_not_over_the_action_bar(app):
    async with app.run_test(size=(100, 30), notifications=True) as pilot:
        toasts = await shown_toasts(app, pilot, timeout=30)
        rack_top = min(t.region.y for t in toasts.values())
        rack_bottom = max(t.region.bottom for t in toasts.values())
        assert rack_top >= 3 and rack_bottom < app.size.height - 8
        assert all(t.region.right <= app.size.width for t in toasts.values())


async def test_notice_text_with_brackets_is_shown_literally(app):
    async with app.run_test(size=(100, 30), notifications=True) as pilot:
        app.notify("Added to queue: Lofi [beats to relax] mix", timeout=30)
        app.screen.notify("From a screen: [x] done", timeout=30)
        await pilot.pause(0.5)
        shown = {t.render().plain for t in app.screen.query(Toast)}
    assert shown == {"Added to queue: Lofi [beats to relax] mix", "From a screen: [x] done"}
