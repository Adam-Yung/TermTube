"""scripts/setup.sh --refresh: replace the installed code, keep the venv, never touch the network."""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SETUP = Path(__file__).resolve().parents[3] / "scripts" / "setup.sh"

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="needs bash")


@pytest.fixture
def world(tmp_path):
    """A fake checkout and a fake installed app under a fake HOME."""
    repo, home = tmp_path / "repo", tmp_path / "home"
    (repo / "scripts").mkdir(parents=True)
    (repo / "src" / "tui").mkdir(parents=True)
    (repo / "assets").mkdir()
    shutil.copy(SETUP, repo / "scripts" / "setup.sh")
    (repo / "src" / "new.py").write_text("new", encoding="utf-8")
    (repo / "src" / "tui" / "app.py").write_text("app", encoding="utf-8")
    (repo / "src" / "__pycache__").mkdir()
    (repo / "src" / "__pycache__" / "junk.pyc").write_text("x", encoding="utf-8")
    (repo / "assets" / "icon.png").write_text("png", encoding="utf-8")
    (repo / "requirements.txt").write_text("textual\n", encoding="utf-8")
    (repo / "termtube").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "termtube.cmd").write_text("rem\n", encoding="utf-8")
    (repo / "VERSION").write_text("1.2.3", encoding="utf-8")
    app = home / ".local" / "share" / "TermTube"
    (app / ".venv").mkdir(parents=True)
    (app / ".venv" / "marker").write_text("keep me", encoding="utf-8")
    (app / "src").mkdir()
    (app / "src" / "old.py").write_text("stale", encoding="utf-8")
    return repo, home, app


def refresh(repo, home):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
    return subprocess.run(
        ["bash", str(repo / "scripts" / "setup.sh"), "--refresh"], capture_output=True, text=True, env=env
    )


def test_code_is_replaced_and_the_venv_is_kept(world):
    repo, home, app = world
    result = refresh(repo, home)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (app / ".venv" / "marker").read_text(encoding="utf-8") == "keep me"
    assert not (app / "src" / "old.py").exists()
    assert (app / "src" / "new.py").read_text(encoding="utf-8") == "new" and (app / "src" / "tui" / "app.py").exists()
    assert (app / "assets" / "icon.png").exists() and (app / "scripts" / "setup.sh").exists()
    assert not (app / "src" / "__pycache__").exists()
    assert (app / "termtube").stat().st_mode & 0o111 and (app / "VERSION").read_text(encoding="utf-8") == "dev"


def test_it_warns_when_requirements_changed_since_the_venv_was_built(world):
    repo, home, app = world
    (app / ".venv" / ".requirements.sha256").write_text("0" * 64, encoding="utf-8")
    out = refresh(repo, home).stdout
    assert "requirements.txt changed" in out and "downloads packages" in out


def test_it_stays_quiet_when_requirements_match(world):
    repo, home, app = world
    digest = hashlib.sha256((repo / "requirements.txt").read_bytes()).hexdigest()
    (app / ".venv" / ".requirements.sha256").write_text(digest, encoding="utf-8")
    assert "requirements.txt changed" not in refresh(repo, home).stdout


def test_without_an_installed_app_it_refuses_and_creates_nothing(world, tmp_path):
    repo, _, _ = world
    empty_home = tmp_path / "other-home"
    empty_home.mkdir()
    result = refresh(repo, empty_home)
    assert result.returncode == 1 and "No installed app" in result.stdout + result.stderr
    assert not (empty_home / ".local").exists()
