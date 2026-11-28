"""Swift nesting, complexity and body length, by swiftlint with a config written from the caps."""
import json
import tempfile
from pathlib import Path

import config
import lib


def swiftlint_config(caps):
    return "\n".join([
        "only_rules:", "  - nesting", "  - cyclomatic_complexity", "  - function_body_length",
        "  - closure_body_length", "  - function_parameter_count",
        "nesting:", "  type_level: 2", "  function_level: 0",
        "cyclomatic_complexity:", f"  warning: {caps['swift_complexity']}",
        "function_body_length:", f"  warning: {caps['swift_function_lines']}", "",
    ])


def violations(repo):
    files = [p for p in repo.sources("swift") if not config.is_test(p)]
    if not files:
        return []
    with tempfile.TemporaryDirectory(prefix="deslop-swiftlint.") as folder:
        settings = Path(folder, "swiftlint.yml")
        settings.write_text(swiftlint_config(repo.caps))
        cmd = [lib.tool("swiftlint"), "lint", "--config", str(settings), "--reporter", "json", "--quiet", "--no-cache"]
        done = lib.run(cmd + files, repo.root, timeout=600, ok=(0, 2))
    return [
        lib.Violation(f"swift:{v['rule_id']}", lib.relative(repo.root, v["file"]), v["line"] or 1, v["reason"])
        for v in json.loads(done.stdout)
    ]
