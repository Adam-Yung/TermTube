# Brief

Read at the start of every task: it decides what is worth doing.

## Mission
A fast, keyboard-driven YouTube client for the terminal on macOS, Linux and Windows. A human can read its code end to end without an AI agent.

## Who it serves
People who browse, search, listen and watch YouTube without leaving the command line.

## Non-goals
No in-app account login, no telemetry, no writes to the YouTube account, no GUI.

## Anti-goals
A UI that blocks, slow cold start, cookies read where no account is needed, code only an agent can explain.

## Objectives
| id | Objective |
|---|---|
| `browse` | Home, Subscriptions, Search, channels and playlists |
| `playback` | Background audio, queue, video window, resume, SponsorBlock |
| `library` | Downloads, Library, local playlists, history |
| `ui` | Keyboard-driven UI that never blocks, with thumbnails and themes |
| `privacy` | Cookies only where an account is needed; no secrets in logs |
| `install` | Install, update, uninstall and managed binaries on three systems |
| `quality` | Tests, gates, pipeline and developer tools |

## Priorities now
1. Behaviour stays correct.
2. The code stays readable: the gates in `scripts/gate/` only tighten.
3. New features.

## Where to look
`docs/status.md` (present state) · `docs/todo.md` (next work) · `docs/decisions/` (settled calls) · `docs/README.md` (map).
