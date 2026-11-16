"""Linux has no static mpv: the installer links the distro's mpv into the managed bin dir, so the dep check passes."""

import sys

import pytest

from src import bootstrap

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux-only code; symlinks need privileges on Windows")


@pytest.fixture
def linux(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "OS_NAME", "linux")
    system = tmp_path / "usr" / "bin" / "mpv"
    system.parent.mkdir(parents=True)
    system.write_text("#!/bin/sh\n")
    system.chmod(0o755)
    bin_dir = tmp_path / "deps" / "bin"
    bin_dir.mkdir(parents=True)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: str(system) if name == "mpv" else None)
    return system, bin_dir


def test_a_system_mpv_is_linked_into_the_managed_dir(linux):
    system, bin_dir = linux
    assert bootstrap._install_mpv(bin_dir) == "system"
    assert (bin_dir / "mpv").is_symlink() and (bin_dir / "mpv").resolve() == system.resolve()


def test_the_dependency_check_then_passes(linux, monkeypatch):
    from src import deps, plat

    system, bin_dir = linux
    monkeypatch.setattr(plat, "get_deps_bin", lambda: bin_dir)
    assert not plat.is_tool_installed("mpv")
    bootstrap._install_mpv(bin_dir)
    assert plat.is_tool_installed("mpv")
    monkeypatch.setattr(deps, "is_tool_installed", plat.is_tool_installed)
    monkeypatch.setattr(deps, "REQUIRED_TOOLS", ["mpv"])
    assert deps.check_dependencies() is True


def test_running_again_replaces_a_stale_link_and_never_links_to_itself(linux, monkeypatch):
    system, bin_dir = linux
    (bin_dir / "mpv").symlink_to(bin_dir / "gone")
    assert bootstrap._install_mpv(bin_dir) == "system"
    assert (bin_dir / "mpv").resolve() == system.resolve()
    # PATH now leads to the managed link itself (main.py prepends the managed dir)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: str(bin_dir / "mpv"))
    assert bootstrap._install_mpv(bin_dir) == "system"
    assert (bin_dir / "mpv").resolve() == system.resolve()


def test_a_real_file_in_the_managed_dir_is_left_alone(linux):
    system, bin_dir = linux
    (bin_dir / "mpv").write_text("user placed")
    assert bootstrap._install_mpv(bin_dir) == "system"
    assert (bin_dir / "mpv").read_text() == "user placed" and not (bin_dir / "mpv").is_symlink()


def test_without_any_mpv_it_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "OS_NAME", "linux")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)
    assert bootstrap._install_mpv(tmp_path) is None
    assert "apt install mpv" in capsys.readouterr().out
