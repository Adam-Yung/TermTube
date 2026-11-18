"""Layout audit helpers: open a screen at several terminal sizes and report widgets that break the layout rules.

The rules (``docs/decisions/ui.md``, 2026-11-18): nothing protrudes from the screen or from a parent that is not
scrolling, a dialog is centered and fits, sibling controls do not overlap, text has the room it needs.
A scenario list is plain data, so new screens are added by appending a ``Scenario``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from textual.app import App
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Input, ListItem, ListView, OptionList, Static

SIZES = [(80, 24), (100, 30), (120, 40), (160, 50)]
SMALL_SIZE = (60, 20)
CENTER_TOLERANCE = 1  # cells: an even-width dialog on an odd-width screen is off by half a cell

_INTERACTIVE = (Button, Input, ListView, OptionList)


@dataclass(frozen=True)
class Scenario:
    """One screen to audit. ``make`` builds it from the running app; ``dialog`` is the selector of its centered box."""

    name: str
    make: Callable[[App], Screen]
    dialog: str | None = "Vertical"
    small: bool = True
    before: Callable[[App], None] | None = None  # runs before ``make``: fake audio state and the like


def _shown(widget: Widget, stop: Widget) -> bool:
    node: Widget | None = widget
    while node is not None and node is not stop:
        if not node.display:
            return False
        node = node.parent  # type: ignore[assignment]
    return True


def _scrolls(widget: Widget) -> bool:
    """True when the user can scroll the widget: overflowing content under ``overflow: auto`` or ``scroll``."""
    styles = widget.styles
    return (widget.max_scroll_x > 0 and styles.overflow_x in ("auto", "scroll")) or (
        widget.max_scroll_y > 0 and styles.overflow_y in ("auto", "scroll")
    )


def _inside(inner, outer) -> bool:
    return (
        inner.x >= outer.x
        and inner.y >= outer.y
        and inner.right <= outer.right
        and inner.bottom <= outer.bottom
    )


def _label(widget: Widget) -> str:
    return f"{type(widget).__name__}#{widget.id}" if widget.id else type(widget).__name__


def _scrolled_ancestor(widget: Widget, stop: Widget) -> bool:
    node = widget.parent
    while node is not None and node is not stop:
        if isinstance(node, Widget) and _scrolls(node):
            return True
        node = node.parent
    return False


def _text_problem(widget: Static) -> str | None:
    """A Static whose content needs more lines than its box has."""
    width = widget.content_region.width
    if width <= 0:
        return None
    needed = widget.visual.get_height(widget.styles, width)
    if needed > widget.content_region.height:
        return f"text needs {needed} lines, box has {widget.content_region.height}"
    return None


def audit_screen(screen: Screen, *, dialog: str | None, centered_vertically: bool = True) -> list[str]:
    """Return the layout problems of ``screen`` as strings; empty when it follows the rules."""
    problems: list[str] = []
    area = screen.region
    widgets = [w for w in screen.walk_children(Widget) if w.region.area and _shown(w, screen)]

    if dialog:
        found = screen.query(dialog)
        if not found:
            return [f"dialog {dialog} not found"]
        box = found.first().region
        if not _inside(box, area):
            problems.append(f"dialog {box} does not fit the screen {area}")
        if abs((box.x + box.width / 2) - area.width / 2) > CENTER_TOLERANCE:
            problems.append(f"dialog not centered horizontally: {box} on {area.width} wide")
        if centered_vertically and abs((box.y + box.height / 2) - area.height / 2) > CENTER_TOLERANCE:
            problems.append(f"dialog not centered vertically: {box} on {area.height} high")

    for widget in widgets:
        if _scrolled_ancestor(widget, screen):
            continue
        if not _inside(widget.region, area):
            problems.append(f"{_label(widget)} {widget.region} protrudes from the screen")
        parent = widget.parent
        if isinstance(parent, Widget) and parent is not screen and not _scrolls(parent):
            if not _inside(widget.region, parent.content_region):
                problems.append(
                    f"{_label(widget)} {widget.region} protrudes from {_label(parent)} {parent.content_region}"
                )
        if isinstance(widget, Static) and not isinstance(widget, ListItem):
            issue = _text_problem(widget)
            if issue:
                problems.append(f"{_label(widget)}: {issue}")

    by_parent: dict[Widget, list[Widget]] = {}
    for widget in widgets:
        if isinstance(widget, _INTERACTIVE) and widget.parent is not None:
            by_parent.setdefault(widget.parent, []).append(widget)  # type: ignore[arg-type]
    for siblings in by_parent.values():
        for i, a in enumerate(siblings):
            for b in siblings[i + 1 :]:
                if a.region.overlaps(b.region):
                    problems.append(f"{_label(a)} overlaps {_label(b)}")

    for lv in (w for w in widgets if isinstance(w, (ListView, OptionList))):
        if _scrolls(lv):
            continue
        for item in lv.children if isinstance(lv, ListView) else []:
            if item.display and not _inside(item.region, lv.content_region):
                problems.append(f"{_label(lv)} entry {item.region} drawn outside the list {lv.content_region}")
    return problems


async def audit_scenario(app: App, pilot, scenario: Scenario, sizes: list[tuple[int, int]]) -> list[str]:
    """Open the scenario's screen once, audit it at every size, and return ``"name WxH: problem"`` lines."""
    if scenario.before:
        scenario.before(app)
    screen = scenario.make(app)
    app.push_screen(screen)
    await pilot.pause(0.2)
    out: list[str] = []
    for width, height in sizes:
        await pilot.resize_terminal(width, height)
        await pilot.pause(0.2)
        out += [f"{scenario.name} {width}x{height}: {p}" for p in audit_screen(app.screen, dialog=scenario.dialog)]
    app.pop_screen()
    await pilot.pause(0.1)
    return out


MAIN_SIZES = [(80, 24), (100, 30), (120, 40), (160, 50)]
MIN_LIST_WIDTH = 40  # a row shows a title, a badge and the key fields: below this it wraps into noise
MIN_DETAIL_WIDTH = 28
MIN_ROW_TEXT = 28  # cells for the title line of a row
MIN_INFO_ROWS = 6  # title, channel, stats, and a little description: the detail panel's reason to exist


@dataclass(frozen=True)
class ScreenScenario:
    """A main or channel screen state. ``setup`` drives the running app into it once, at the first size."""

    name: str
    setup: Callable[[App, object], Awaitable[None]]


def _stacked(screen: Screen, ids: list[str]) -> list[str]:
    """The named full-width bars must follow each other top to bottom without overlapping."""
    found = [(i, screen.query_one(i).region) for i in ids if screen.query(i)]
    return [
        f"{a} {ra} overlaps {b} {rb}"
        for (a, ra), (b, rb) in zip(found, found[1:], strict=False)
        if ra.bottom > rb.y and rb.area and ra.area
    ]


def audit_main(screen: Screen, *, list_id: str, detail_id: str, rail: bool = False) -> list[str]:
    """Rules for a screen made of bars, a list column and a detail column (``docs/decisions/ui.md``, 2026-11-18)."""
    problems = audit_screen(screen, dialog=None)
    area = screen.region
    problems += _stacked(screen, ["AppHeader", "#nav-tabs", "#main-content", "Footer"])
    footer = screen.query_one("Footer").region
    if footer.bottom != area.bottom or not footer.area:
        problems.append(f"footer {footer} is not the last row of the screen {area}")
    panel = screen.query_one(list_id)
    if panel.region.width < MIN_LIST_WIDTH:
        problems.append(f"list is {panel.region.width} wide, minimum {MIN_LIST_WIDTH}")
    detail = screen.query_one(detail_id)
    if detail.display and detail.region.width < MIN_DETAIL_WIDTH:
        problems.append(f"detail panel is {detail.region.width} wide, minimum {MIN_DETAIL_WIDTH}")
    if detail.display and detail.region.height >= 1:
        info = detail.query_one("#video-info")
        if info.display and info.region.height < MIN_INFO_ROWS:
            problems.append(f"detail info has {info.region.height} rows, minimum {MIN_INFO_ROWS}")
    lv = panel.query_one("ListView")
    for item in lv.children:
        if item.display and item.region.height and not _inside_x(item.region, lv.region):
            problems.append(f"row {item.region} not inside the list {lv.region}")
        text = item.query("Static")
        if item.display and item.region.height and text and text.first().content_region.width < MIN_ROW_TEXT:
            problems.append(f"row text has {text.first().content_region.width} cells, minimum {MIN_ROW_TEXT}")
    indicator = panel.query_one("PageIndicator")
    if indicator.render().cell_len > indicator.region.width:
        problems.append(f"page indicator '{indicator.render().plain}' wider than its {indicator.region.width} cells")
    if rail:
        rail_widget = screen.query_one("#library-rail")
        if rail_widget.display and rail_widget.region.width < 12:
            problems.append(f"rail is {rail_widget.region.width} wide")
        if rail_widget.display:
            for line in rail_widget.render().split("\n"):
                if line.cell_len > rail_widget.content_region.width:
                    problems.append(f"rail line '{line.plain}' is wider than {rail_widget.content_region.width} cells")
    return problems


def _inside_x(inner, outer) -> bool:
    return inner.x >= outer.x and inner.right <= outer.right


async def settle(pilot, problems_fn, tries: int = 100) -> list[str]:
    """Pause until ``problems_fn()`` is empty (a layout pass can lag a resize), ``tries`` times at most."""
    found = problems_fn()
    for _ in range(tries):
        if not found:
            break
        await pilot.pause()
        found = problems_fn()
    return found


async def audit_screen_scenario(
    app: App, pilot, scenario: ScreenScenario, sizes: list[tuple[int, int]], **rules
) -> list[str]:
    """Drive the app into ``scenario``, audit the current screen at every size, return ``"name WxH: problem"`` lines."""
    await pilot.resize_terminal(*sizes[-1])
    await scenario.setup(app, pilot)
    out: list[str] = []
    for width, height in sizes:
        await pilot.resize_terminal(width, height)
        problems = await settle(pilot, lambda: audit_main(app.screen, **rules))
        out += [f"{scenario.name} {width}x{height}: {p}" for p in problems]
    return out
