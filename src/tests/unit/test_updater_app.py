"""update_app_code against a fake GitHub release: what is replaced, and when nothing is touched."""

import io
import json
import zipfile

import pytest

from src import updater


def release(root, files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, body in files.items():
            zf.writestr(f"{root}/{name}", body)
    return out.getvalue()


class GitHub:
    """A fake GitHub release ``v2.0``; ``asked`` collects requested URLs and pip commands."""

    def __init__(self):
        self.asked, self.archive = [], None

    def urlopen(self, req, timeout=None):
        self.asked.append(req.full_url)
        if "api.github.com" in req.full_url:
            return io.BytesIO(json.dumps({"tag_name": "v2.0"}).encode())
        if self.archive is None:
            raise OSError("boom")
        return io.BytesIO(self.archive)

    def run(self, cmd, **kwargs):
        self.asked.append(cmd)

    def __call__(self, archive):
        self.archive = archive
        return self.asked


@pytest.fixture
def github(monkeypatch):
    fake = GitHub()
    monkeypatch.setattr("urllib.request.urlopen", fake.urlopen)
    monkeypatch.setattr(updater.subprocess, "run", fake.run)
    return fake


def installed(tmp_path, version):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "old.py").write_text("old", encoding="utf-8")
    (tmp_path / "VERSION").write_text(version, encoding="utf-8")
    return tmp_path


def test_a_new_release_replaces_src_and_records_the_tag(tmp_path, github, capsys):
    install = installed(tmp_path, "v1.0")
    github(release("TermTube-2.0", {"src/new.py": "new", "scripts/s.sh": "s"}))
    assert updater.update_app_code(install, verbose=True) is True
    assert [p.name for p in (install / "src").iterdir()] == ["new.py"]
    assert (install / "scripts" / "s.sh").exists()
    assert (install / "VERSION").read_text(encoding="utf-8") == "v2.0"
    out = capsys.readouterr().out
    assert "Downloading update..." in out and "[ok] app: updated to v2.0" in out


def test_an_unexpected_folder_name_is_still_found_and_requirements_installed(tmp_path, github, monkeypatch):
    install = installed(tmp_path, "v1.0")
    monkeypatch.setattr(updater, "IS_WINDOWS", False)
    pip = install / ".venv" / "bin" / "pip3"
    pip.parent.mkdir(parents=True)
    pip.write_text("", encoding="utf-8")
    asked = github(release("other", {"src/new.py": "new", "requirements.txt": ""}))
    assert updater.update_app_code(install) is True
    assert asked[-1][0] == str(pip) and asked[-1][1:3] == ["install", "-r"]


@pytest.mark.parametrize("version,line", [("dev", "dev install"), ("v2.0", "already on v2.0")])
def test_nothing_is_downloaded_when_current_or_dev(tmp_path, github, capsys, version, line):
    install = installed(tmp_path, version)
    asked = github(None)
    assert updater.update_app_code(install, verbose=True) is True
    assert len(asked) == 1 and line in capsys.readouterr().out
    assert (install / "src" / "old.py").exists()


def test_a_failed_download_changes_nothing(tmp_path, github, capsys):
    install = installed(tmp_path, "v1.0")
    github(None)
    assert updater.update_app_code(install, verbose=True) is False
    assert "App update failed: boom" in capsys.readouterr().out
    assert (install / "VERSION").read_text(encoding="utf-8") == "v1.0"


def test_an_archive_without_a_folder_is_refused(tmp_path, github, capsys):
    install = installed(tmp_path, "v1.0")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w"):
        pass
    github(out.getvalue())
    assert updater.update_app_code(install, verbose=True) is False
    assert "Could not find extracted directory." in capsys.readouterr().out


def test_an_unreachable_github_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert updater.update_app_code(tmp_path, verbose=True) is False
    assert "Could not reach GitHub" in capsys.readouterr().out
