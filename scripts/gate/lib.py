"""Shared plumbing of the gates: bounded subprocesses, git, globs, the command line and the exit status."""
import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent
ASK = "ask the owner before installing"
HINTS = {
    "ruff": "`brew install ruff` or `pip install ruff`",
    "shellcheck": "`brew install shellcheck`",
    "swiftlint": "`brew install swiftlint`",
    "cargo": "install Rust with rustup, then `rustup component add clippy`",
    "eslint": "`npm install --save-dev eslint`",
    "jscpd": "`npm install --save-dev jscpd`",
}
WILD = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}


class GateError(Exception):
    """The gate could not judge the tree; it fails rather than guess."""


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    message: str


def hint(name):
    return f"{HINTS.get(name, name)} ({ASK})"


def run(cmd, cwd, timeout=120, env=None, ok=(0,)):
    name = Path(cmd[0]).name
    try:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env, errors="replace")
    except FileNotFoundError:
        raise GateError(f"{name} is missing: {hint(name)}")
    except subprocess.TimeoutExpired:
        raise GateError(f"{name} did not finish within {timeout} s")
    if done.returncode not in ok:
        raise GateError(f"{name} exited {done.returncode}: {(done.stderr or done.stdout)[-2000:]}")
    return done


def tool(name):
    found = shutil.which(name)
    if not found:
        raise GateError(f"{name} is missing: {hint(name)}")
    return found


def git(root, *args, ok=(0,)):
    return run(["git", "-c", "core.quotePath=false", *args], root, timeout=60, ok=ok).stdout


def read(root, path):
    return (Path(root) / path).read_text(encoding="utf-8", errors="replace")


def glob_pattern(glob):
    """`*` stays in one folder, `**` crosses folders, and naming a folder covers everything in it."""
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", glob.rstrip("/"))
    body = "".join(WILD.get(part, re.escape(part)) for part in parts)
    return re.compile(rf"{body}(?:/.*)?\Z")


def relative(root, path):
    full = Path(path)
    if not full.is_absolute():
        return full.as_posix()
    return full.resolve().relative_to(Path(root).resolve()).as_posix()


def parser(description):
    made = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    made.add_argument("--root", type=Path, default=Path.cwd(), help="repository to check (default: here)")
    made.add_argument("--config", type=Path, help="config file (default: <root>/.deslop.json)")
    return made


def main_guard(body):
    """Exit status of a check: 0 clean, 1 findings, 2 the check itself could not run."""
    try:
        return body()
    except GateError as error:
        print(f"GATE ERROR: {error}")
        return 2


def verdict(problems, name):
    if problems:
        print(f"{name}: failed")
        print("\n".join(problems))
        return 1
    print(f"{name}: ok")
    return 0
