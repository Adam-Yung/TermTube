"""Startup dependency check: only the bundled tools count."""

from src import deps, plat


def test_deps_bin_is_under_the_user_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    monkeypatch.setattr(plat.Path, "home", staticmethod(lambda: tmp_path))
    assert plat.get_deps_bin() == tmp_path / ".local" / "termtube-deps" / "bin"


def test_is_tool_installed_looks_only_in_the_bundled_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    monkeypatch.setattr(plat.Path, "home", staticmethod(lambda: tmp_path))
    bin_dir = tmp_path / ".local" / "termtube-deps" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "mpv").write_text("")
    assert plat.is_tool_installed("mpv") and not plat.is_tool_installed("deno")


def test_system_copies_do_not_satisfy_the_check(monkeypatch, capsys):
    monkeypatch.setattr(deps, "is_tool_installed", lambda name: False)
    monkeypatch.setattr(deps.sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    assert deps.check_dependencies() is False
    out = capsys.readouterr().out
    assert "mpv" in out and "deno" in out and "ffmpeg" in out


def test_all_bundled_tools_pass(monkeypatch):
    monkeypatch.setattr(deps, "is_tool_installed", lambda name: True)
    assert deps.check_dependencies() is True


def test_only_the_missing_tools_are_offered(monkeypatch):
    monkeypatch.setattr(deps, "is_tool_installed", lambda name: name != "ffmpeg")
    monkeypatch.setattr(deps.sys.stdin, "isatty", lambda: True, raising=False)
    offered = []
    monkeypatch.setattr(deps, "_offer_bootstrap", lambda missing: offered.append(missing) or True)
    assert deps.check_dependencies() is True
    assert offered == [["ffmpeg"]]
