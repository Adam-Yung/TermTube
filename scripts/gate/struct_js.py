"""JavaScript and TypeScript depth, complexity, length and nested named functions, by eslint (never npx)."""
import json

import lib

RULES = ("max-depth", "complexity", "max-lines-per-function", "no-restricted-syntax")


def convert(repo, result):
    path = lib.relative(repo.root, result["filePath"])
    broken = [m for m in result["messages"] if m.get("fatal")]
    if broken:
        raise lib.GateError(f"{path}:{broken[0].get('line')}: eslint cannot parse it: {broken[0]['message']}")
    return [
        lib.Violation(f"js:{m['ruleId']}", path, m["line"], m["message"])
        for m in result["messages"]
        if m.get("ruleId") in RULES
    ]


def config_file(repo, files):
    given = repo.cfg["eslint_config"]
    if given:
        return str(repo.root / given)
    typed = [p for p in files if repo.language(p) == "typescript"]
    if typed:
        raise lib.GateError(
            f"{len(typed)} TypeScript file(s): set eslint_config in .deslop.json to a flat config with a TypeScript "
            f"parser (`npm install --save-dev typescript-eslint`, {lib.ASK})")
    return str(lib.SKILL_SCRIPTS / "lint" / "eslint.config.mjs")


def limit_rules(caps):
    rules = {
        "max-depth": ["error", caps["js_depth"]],
        "complexity": ["error", caps["js_complexity"]],
        "max-lines-per-function": ["error", {"max": caps["js_function_lines"]}],
    }
    return ["--rule", json.dumps(rules)]


def violations(repo):
    files = repo.sources("javascript", "typescript")
    if not files:
        return []
    cmd = [
        repo.node_tool("eslint"), "--no-config-lookup", "--config", config_file(repo, files), *limit_rules(repo.caps),
        "--no-inline-config", "--no-warn-ignored", "--format", "json",
    ]
    done = lib.run(cmd + files, repo.root, timeout=300, ok=(0, 1))
    return [item for result in json.loads(done.stdout) for item in convert(repo, result)]
