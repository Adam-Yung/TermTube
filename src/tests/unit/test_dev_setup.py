"""scripts/dev-setup.sh --check: the dev venv must be its own directory, separate from the installed app's."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev-setup.sh"

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="needs bash")


def make_venv(path: Path) -> None:
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(path)], check=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "dev-setup.sh")
    (root / "requirements-dev.txt").write_text("")
    return root


def check(repo, tmp_path, app=None):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "TERMTUBE_APP_DIR": str(app or tmp_path / "no-app")}
    return subprocess.run(
        ["bash", str(repo / "scripts" / "dev-setup.sh"), "--check"], capture_output=True, text=True, env=env
    )


def test_a_separate_venv_passes_and_app_install_is_optional(repo, tmp_path):
    make_venv(repo / ".venv")
    result = check(repo, tmp_path)
    assert result.returncode == 0, result.stdout
    assert "venv is a real directory" in result.stdout and "nothing to clash with" in result.stdout


def test_a_missing_venv_fails_with_the_fix(repo, tmp_path):
    result = check(repo, tmp_path)
    assert result.returncode == 1 and "dev-setup.sh --install" in result.stdout


def test_a_symlinked_dev_venv_is_a_failure(repo, tmp_path):
    make_venv(tmp_path / "elsewhere")
    (repo / ".venv").symlink_to(tmp_path / "elsewhere")
    result = check(repo, tmp_path)
    assert result.returncode == 1 and ".venv is a symlink" in result.stdout


def test_dev_and_app_venv_being_the_same_directory_is_a_failure(repo, tmp_path):
    make_venv(repo / ".venv")
    app = tmp_path / "app"
    app.mkdir()
    (app / ".venv").symlink_to(repo / ".venv")
    result = check(repo, tmp_path, app=app)
    assert result.returncode == 1 and "same directory" in result.stdout


def test_a_link_from_the_dev_venv_into_the_app_install_is_a_failure(repo, tmp_path):
    make_venv(repo / ".venv")
    app = tmp_path / "app"
    make_venv(app / ".venv")
    (repo / ".venv" / "lib" / "shared").symlink_to(app / ".venv" / "lib")
    result = check(repo, tmp_path, app=app)
    assert result.returncode == 1 and "links from the dev venv into the app install" in result.stdout


def test_a_pip_from_another_venv_is_a_failure(repo, tmp_path):
    make_venv(repo / ".venv")
    pip = repo / ".venv" / "bin" / "pip"
    pip.write_text(f"#!{tmp_path}/other/bin/python\n")
    pip.chmod(0o755)
    result = check(repo, tmp_path)
    assert result.returncode == 1 and "a copied venv" in result.stdout
