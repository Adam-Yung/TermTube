"""``thumbnail_format: symbols`` forces half-block art even where pixel images work."""

from __future__ import annotations

import pytest

from src.config import Config
from src.tui.widgets import thumbnail_widget


@pytest.mark.parametrize(
    ("capable", "fmt", "expected"),
    [
        (True, "auto", True),
        (True, "symbols", False),
        (False, "auto", False),
        (False, "symbols", False),
    ],
)
def test_pixel_images_enabled(tmp_path, monkeypatch, capable, fmt, expected):
    monkeypatch.setattr(thumbnail_widget, "_HAS_TEXTUAL_IMAGE", capable)
    config = Config(path=str(tmp_path / "config.yaml"))
    config.set("thumbnail_format", fmt)
    assert thumbnail_widget.pixel_images_enabled(config) is expected


def test_loader_renders_blocks_when_symbols_chosen(tmp_path, monkeypatch):
    from src.tui import thumb_loader

    monkeypatch.setattr(thumbnail_widget, "_HAS_TEXTUAL_IMAGE", True)
    config = Config(path=str(tmp_path / "config.yaml"))
    config.set("thumbnail_format", "symbols")

    calls: list[tuple] = []

    class App:
        def __init__(self) -> None:
            self.config = config

        def call_from_thread(self, fn, *args):
            fn(*args)

    class Target:
        def set_thumbnail_ansi(self, vid, ansi):
            calls.append(("ansi", vid, ansi))

        def set_thumbnail_image(self, vid, path):
            calls.append(("image", vid))

        def set_thumbnail_placeholder(self):
            calls.append(("placeholder",))

    def no_pixel(*a, **k):
        raise AssertionError("pixel path used although symbols was chosen")

    monkeypatch.setattr(thumb_loader.thumbnail, "ensure_thumb_jpeg", no_pixel)
    monkeypatch.setattr(thumb_loader.thumbnail, "render_pil_halfblock", lambda *a, **k: "ART")
    vid = "sym" + "x" * 8
    thumb_loader.load_thumbnail(App(), Target(), vid, entry={"id": vid}, is_current=lambda: True)
    assert calls == [("ansi", vid, "ART")]
