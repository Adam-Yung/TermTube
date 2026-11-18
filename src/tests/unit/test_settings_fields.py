"""Validation behind the Settings rows: a refusal carries a one-line reason."""

import pytest

from src.config import Config
from src.tui.settings_fields import (
    FIELDS,
    SECTIONS,
    Refused,
    browser_status,
    parse_categories,
    parse_dir,
    parse_int,
    parse_template,
)


def test_dir_accepts_an_existing_and_a_creatable_directory(tmp_path):
    assert parse_dir(f"  {tmp_path}  ") == str(tmp_path)
    assert parse_dir(str(tmp_path / "a" / "b")) == str(tmp_path / "a" / "b")


def test_dir_refuses_empty_relative_and_a_file(tmp_path):
    (tmp_path / "f").write_text("x", encoding="utf-8")
    for text, reason in (("", "Enter a directory"), ("rel/dir", "absolute"), (str(tmp_path / "f" / "x"), "is a file")):
        with pytest.raises(Refused, match=reason):
            parse_dir(text)


@pytest.mark.parametrize("text", ["", "../x.%(ext)s", "/abs/x.%(ext)s", "a/../x.%(ext)s", "C:\\x.%(ext)s"])
def test_template_reuses_the_download_guard(text):
    with pytest.raises(Refused, match="relative path without"):
        parse_template(text)


def test_template_accepts_subfolders():
    assert parse_template("%(uploader)s/%(title)s.%(ext)s") == "%(uploader)s/%(title)s.%(ext)s"


def test_int_range_and_text():
    parse = parse_int(10, 50)
    assert parse(" 20 ") == 20 and parse("10") == 10 and parse("50") == 50
    bad = (("9", "from 10 to 50"), ("51", "from 10 to 50"), ("x", "whole number"), ("2.5", "whole number"))
    for text, reason in bad:
        with pytest.raises(Refused, match=reason):
            parse(text)


def test_categories_are_checked_and_deduplicated():
    assert parse_categories("sponsor, intro  sponsor") == ["sponsor", "intro"]
    with pytest.raises(Refused, match="at least one"):
        parse_categories(" , ")
    with pytest.raises(Refused, match="Unknown: nope"):
        parse_categories("sponsor nope")


def test_browser_status_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("src.browsers.detect_installed_browsers", lambda: [])
    config = Config(path=str(tmp_path / "c.yaml"))
    assert "no supported browser" in browser_status(config)
    config.set("browser", "none")
    assert "signed out" in browser_status(config)
    config.set("browser", "chrome")
    assert browser_status(config).startswith("chrome")


def test_every_field_belongs_to_a_section_and_shows_a_value(tmp_path):
    config = Config(path=str(tmp_path / "c.yaml"))
    assert {f.section for f in FIELDS} <= set(SECTIONS)
    for fld in FIELDS:
        if fld.kind not in ("action", "info"):
            assert fld.show(config) != "" or fld.key == "browser"
            config.reset(fld.key)
