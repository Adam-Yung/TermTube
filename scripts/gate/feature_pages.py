"""Reads the objectives table and the Serves and Owns lines of the feature pages."""
import re
from dataclasses import dataclass

import lib

HEAD_LINES = 15
SERVES = re.compile(r"^> Serves:(.+)$")
OWNS = re.compile(r"^> Owns:(.+)$")
ROW = re.compile(r"^\|\s*`([\w-]+)`\s*\|")


@dataclass
class Page:
    path: str
    name: str
    serves: list
    owns: list


def objectives(repo):
    source, heading = repo.cfg["objectives_file"], repo.cfg["objectives_heading"]
    if not (repo.root / source).is_file():
        raise lib.GateError(f"{source} is missing")
    section = re.search(rf"^## {re.escape(heading)}$(.*?)(?=^## |\Z)", repo.read(source), re.M | re.S)
    found = {m.group(1) for m in map(ROW.match, section.group(1).splitlines()) if m} if section else set()
    if not found:
        raise lib.GateError(f"{source} has no `## {heading}` table whose first column holds backticked ids")
    return found


def page(repo, path):
    head = repo.read(path).splitlines()[:HEAD_LINES]
    serves = [i for m in map(SERVES.match, head) if m for i in re.findall(r"[\w-]+", m.group(1))]
    owns = [g for m in map(OWNS.match, head) if m for g in re.findall(r"`([^`]+)`", m.group(1))]
    return Page(path, path.rsplit("/", 1)[-1], serves, owns)


def load(repo):
    folder = re.escape(repo.cfg["feature_dir"].rstrip("/"))
    paths = [p for p in repo.files() if re.fullmatch(rf"{folder}/[^/]+\.md", p) and not p.endswith("/README.md")]
    return [page(repo, p) for p in paths]
