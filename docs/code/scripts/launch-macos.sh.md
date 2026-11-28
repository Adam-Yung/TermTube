# scripts/launch-macos.sh

Opens a terminal window and runs TermTube in it: kitty, WezTerm, Ghostty or iTerm2 if installed (in that order), else Terminal.app. Called by the `TermTube.app` launcher that [setup.sh](setup.sh.md) writes; argument is the absolute path of the `termtube` launcher.

## Graphics terminals first

Terminal.app has no image protocol (no Kitty graphics, Sixel or iTerm2 images), so thumbnails fall back to block-character pixel art, and it always goes through the user's login shell. The four preferred terminals support real images and run a command directly, so none of the workarounds below apply to them. Invocations: `open -n kitty.app --args <termtube>`, `open -n WezTerm.app --args start -- <termtube>`, `open -n Ghostty.app --args -e <termtube>`, and an AppleScript `create window with default profile command` for iTerm2. It looks in `/Applications` and `~/Applications`. `TERMTUBE_TERMINAL=terminal` forces Terminal.app. Only the kitty path has been run; the other three are from their documentation.

## Terminal.app: why it does not just type the command

Terminal.app always starts the user's login shell, so their rc files run first, and we cannot know what they do. A `.zshrc` that runs `tmux new-session -A -s main` blocks there, and TermTube must not end up inside tmux. `.terminal` profiles with `RunCommandAsShell` off were tried and still go through the login shell, so there is no way to skip the rc files on Terminal.app.

## Behaviour

1. Opens an empty window (`do script ""`) and reads its tty.
2. Polls `ps -t <tty>` every 0.5 s (minus the `login` wrapper):
   - a `tmux` client on the tty (the user's rc auto-attached): finds it with `tmux list-clients` and runs `tmux detach-client` on it, so an rc that just runs `tmux new-session` falls through to a plain prompt and TermTube runs outside tmux. If the rc `exec`ed tmux, the window dies on detach and it falls back to `tmux new-window` in that session;
   - exactly one process for three polls in a row (the shell is idle at its prompt): types `exec '<termtube>'` into that tab;
   - 30 s timeout: types the command anyway.
3. `exec` makes the window close when TermTube exits cleanly.

## Limits

- Other multiplexers (screen, zellij) are not special-cased; the typed command goes into them.
- A shell whose startup runs a child process the whole time delays the typing until the timeout.
- Tested by hand with the plain shell and with a tmux auto-attach (fake `termtube`); no automated test, because it opens real Terminal windows. `TERMTUBE_LAUNCH_NOOPEN=1` plus `TERMTUBE_LAUNCH_TTY` lets a test point it at an existing tty.

Reviewed: 246af469
