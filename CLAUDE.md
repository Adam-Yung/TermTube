# TermTube: instructions for Claude Code

Read `AGENTS.md` first. Its first block is a hard rule that overrides everything else: never download, fetch or load anything a platform has
flagged, that cannot be verified, or without asking; tests never touch the network or the user's browser profile. Every prompt to a subagent
that may touch the network must repeat the rule and forbid downloading.

Model budget rule (also in `AGENTS.md`): never use an Opus model; use Sonnet or smaller for the session and every subagent (set
`model: "sonnet"` when spawning), and keep usage light because the token budget is very limited.

`AGENTS.md` also holds the documentation structure, the `docs/code/` mirror rule, comment and writing style, and the commit gate
(`scripts/verify.sh`). `docs/status.md` says where things stand; `docs/features/architecture.md` is the wiring map.
