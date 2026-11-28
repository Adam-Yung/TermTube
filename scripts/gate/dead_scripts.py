"""Scripts in the scripts folder that nothing but the index and their own mirror mentions."""
import re

import config
import lib

SCRIPTS = (".sh", ".py", ".mjs", ".js", ".swift", ".rb")
BINARY = (".png", ".jpg", ".jpeg", ".pptx", ".ttf", ".pdf", ".docx", ".xlsx", ".icns", ".gif", ".zip", ".gz", ".bin")


def candidates(repo):
    folder = repo.cfg["scripts_dir"].rstrip("/") + "/"
    return [
        p for p in repo.files()
        if p.startswith(folder) and p.endswith(SCRIPTS) and not repo.outside(p) and not config.is_test(p)
    ]


def pattern(script):
    """The file name as a whole word, or for Python an import of the module."""
    name = script.rsplit("/", 1)[-1]
    found = rf"(?<![\w.-]){re.escape(name)}(?![\w-])"
    if name.endswith(".py"):
        stem = re.escape(name[:-3])
        found += rf"|^\s*(?:from\s+{stem}\s+import|import\s+(?:[\w.]+\s*,\s*)*{stem}\b)"
    return re.compile(found, re.M)


def corpus(repo):
    baselines = repo.cfg["baseline_dir"] + "/"
    return {
        path: repo.read(path)
        for path in repo.files()
        if path != repo.cfg["scripts_index"] and not path.startswith(baselines) and not path.endswith(BINARY)
    }


def referenced(repo, script, texts):
    wanted = pattern(script)
    stem = script.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    own = {script, f"{repo.cfg['mirror_dir']}/{script}.md"}
    # The substring test first: the regex over every file for every script is slow.
    return any(stem in text and wanted.search(text) for path, text in texts.items() if path not in own)


def violations(repo):
    found = candidates(repo)
    if not found:
        return []
    texts = corpus(repo)
    return [
        lib.Violation("script-unreferenced", script, 1, "only the index and its own mirror mention it")
        for script in found
        if not referenced(repo, script, texts)
    ]
