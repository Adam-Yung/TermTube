"""Temp and IPC directories are created 0700 and refused when they are not ours."""

import os
import stat
import sys

import pytest

from src import logger, plat

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")


def test_creates_the_directory_private(tmp_path):
    made = plat.private_dir(tmp_path / "a" / "ipc")
    assert stat.S_IMODE(made.stat().st_mode) == 0o700


def test_tightens_a_loose_directory_of_ours(tmp_path):
    loose = tmp_path / "loose"
    loose.mkdir(mode=0o755)
    loose.chmod(0o755)
    plat.private_dir(loose)
    assert stat.S_IMODE(loose.stat().st_mode) == 0o700


def test_refuses_a_symlink(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(PermissionError):
        plat.private_dir(link)


def test_refuses_a_directory_of_another_user(tmp_path, monkeypatch):
    theirs = tmp_path / "theirs"
    theirs.mkdir()
    monkeypatch.setattr(plat.os, "getuid", lambda: os.stat(theirs).st_uid + 1)
    with pytest.raises(PermissionError):
        plat.private_dir(theirs)


def test_refuses_a_plain_file(tmp_path):
    f = tmp_path / "file"
    f.write_text("x", encoding="utf-8")
    with pytest.raises((PermissionError, FileExistsError)):
        plat.private_dir(f)


def test_ipc_path_fails_closed_on_an_untrusted_runtime_dir(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "run"
    link.symlink_to(target)
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(link))
    with pytest.raises(PermissionError):
        plat.get_audio_ipc_path()


def test_debug_log_is_not_written_into_an_untrusted_directory(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "logs"
    link.symlink_to(target)
    monkeypatch.setattr(logger, "_LOG_DIR", link)
    try:
        logger.setup(debug=True)
        assert list(target.iterdir()) == []
    finally:
        logger.setup(debug=False)
