"""A throwaway git repository, and a gate script run against it.

DESLOP_TEST_TMP        where the throwaway repositories are made (default: the system temp folder)
DESLOP_TEST_NODE_BIN   a node_modules/.bin holding eslint and jscpd; without it their tests are skipped
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
NODE_BIN = os.environ.get("DESLOP_TEST_NODE_BIN")
LIMIT = 600


def has(name):
    return bool(shutil.which(name))


def has_node(name):
    return bool(NODE_BIN and (Path(NODE_BIN) / name).exists()) or has(name)


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    env.update(extra)
    return env


class GateCase(unittest.TestCase):
    def setUp(self):
        made = tempfile.TemporaryDirectory(prefix="deslop-test.", dir=os.environ.get("DESLOP_TEST_TMP"))
        self.addCleanup(made.cleanup)
        self.root = Path(made.name).resolve()
        self.git("init", "-q")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, env=clean_env(), timeout=LIMIT)

    def write(self, path, text):
        full = self.root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text)

    def configure(self, **settings):
        if NODE_BIN:
            settings.setdefault("node_bin", [NODE_BIN])
        self.write(".deslop.json", json.dumps(settings))

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "fixture")

    def gate(self, script, *args, env=None):
        cmd = [sys.executable, str(SCRIPTS / script), "--root", str(self.root), *args]
        done = subprocess.run(cmd, capture_output=True, text=True, env=env or clean_env(), timeout=LIMIT)
        return done.returncode, done.stdout + done.stderr

    def assert_status(self, wanted_status, script, args, wanted, env=None):
        status, out = self.gate(script, *args, env=env)
        self.assertEqual(status, wanted_status, out)
        for text in wanted:
            self.assertIn(text, out)
        return out

    def assertPasses(self, script, *args):
        return self.assert_status(0, script, args, ())

    def assertFails(self, script, *wanted, args=()):
        return self.assert_status(1, script, args, wanted)

    def assertCannotRun(self, script, *wanted, args=(), env=None):
        return self.assert_status(2, script, args, wanted, env=env)

    def path_with_only(self, *names):
        """An environment whose PATH holds just these tools: how a missing analyzer looks."""
        made = tempfile.TemporaryDirectory(prefix="deslop-bin.", dir=os.environ.get("DESLOP_TEST_TMP"))
        self.addCleanup(made.cleanup)
        for name in names:
            os.symlink(shutil.which(name), Path(made.name) / name)
        return clean_env(PATH=made.name)
