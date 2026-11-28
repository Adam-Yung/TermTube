"""Rust nesting, cognitive complexity and function length: clippy's JSON, counted, never denied in Cargo.toml."""
import json
import os
import tempfile
from pathlib import Path

import lib

LINTS = ("excessive_nesting", "cognitive_complexity", "too_many_lines")


def primary(message):
    for span in message["spans"]:
        if span["is_primary"]:
            return span["file_name"], span["line_start"], span["column_start"]
    return None


def parse(line):
    """(lint, file, line, column, text) of a diagnostic this gate counts, else None."""
    if not line.startswith("{"):
        return None
    record = json.loads(line)
    if record.get("reason") != "compiler-message":
        return None
    message = record["message"]
    lint = (message.get("code") or {}).get("code", "").replace("clippy::", "")
    where = primary(message)
    if lint not in LINTS or not where:
        return None
    return (lint, *where, message["message"])


def clippy_toml(caps):
    return (f"excessive-nesting-threshold = {caps['rust_nesting']}\n"
            f"cognitive-complexity-threshold = {caps['rust_complexity']}\n"
            f"too-many-lines-threshold = {caps['rust_function_lines']}\n")


def workspaces(repo, files):
    """The outermost folders with a Cargo.toml that hold the judged files."""
    manifests = sorted({str(Path(p).parent) for p in repo.files() if Path(p).name == "Cargo.toml"}, key=len)
    chosen = set()
    for path in files:
        parents = [str(p) for p in Path(path).parents]
        owner = next((m for m in manifests if m in parents), None)
        if owner is None:
            raise lib.GateError(f"{path}: no Cargo.toml above it, clippy cannot judge it")
        chosen.add(owner)
    return sorted(chosen)


def clippy(repo, folder, conf):
    cmd = [lib.tool("cargo"), "clippy", "--offline", "--workspace", "--all-targets", "--all-features",
           "--message-format=json", "--"]
    for lint in LINTS:
        cmd += ["--force-warn", f"clippy::{lint}"]
    done = lib.run(cmd, repo.root / folder, timeout=900, env=dict(os.environ, CLIPPY_CONF_DIR=conf))
    found = filter(None, map(parse, done.stdout.splitlines()))
    # clippy names files relative to the workspace it ran in.
    return {(lint, os.path.normpath(os.path.join(folder, name)), *rest) for lint, name, *rest in found}


def violations(repo):
    files = repo.sources("rust")
    if not files:
        return []
    with tempfile.TemporaryDirectory(prefix="deslop-clippy.") as conf:
        Path(conf, "clippy.toml").write_text(clippy_toml(repo.caps))
        # A file built into both the library and its tests reports twice, hence the set.
        found = set().union(*(clippy(repo, folder, conf) for folder in workspaces(repo, files)))
    judged = set(files)
    return [lib.Violation(f"rust:{lint}", path, line, text)
            for lint, path, line, _, text in sorted(found) if path in judged]
