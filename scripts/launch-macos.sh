#!/bin/bash
# Opens a terminal window and runs TermTube in it (kitty, WezTerm, Ghostty or iTerm2 if installed, else Terminal.app), whatever the user's shell startup files do.
# Usage: launch-macos.sh /path/to/termtube
#
# Terminal.app always starts the user's login shell, so rc files run first and may block (tmux
# auto-attach), print prompts or start other multiplexers. Typing the command blindly can land in the
# wrong place. So: open an empty window, watch what runs on its tty, and then
#   - plain idle shell        -> type `exec termtube` into it
#   - tmux took over          -> detach that client so the rc falls through to a plain prompt, then as above
#                               (if the rc exec'd tmux and the window closes, run in a new tmux window instead)
#   - anything else / timeout -> type the command anyway (best effort)
# TERMTUBE_LAUNCH_NOOPEN=1 skips opening a window (tests): the tty is then read from TERMTUBE_LAUNCH_TTY.

set -u
BIN="${1:?usage: launch-macos.sh /path/to/termtube}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
TIMEOUT_TICKS="${TERMTUBE_LAUNCH_TICKS:-60}"   # x0.5 s

# Preferred: a terminal with real image support (Kitty graphics / Sixel) that runs a command directly,
# with no login shell and so no rc files. Terminal.app has no image protocol (thumbnails fall back to
# block-character pixel art). TERMTUBE_TERMINAL=terminal forces Terminal.app.
find_app() {
    local a
    for a in "/Applications/$1.app" "$HOME/Applications/$1.app"; do
        [[ -d "$a" ]] && { echo "$a"; return 0; }
    done
    return 1
}

launch_graphics_terminal() {
    local app
    if app=$(find_app kitty); then
        open -n "$app" --args "$BIN" && return 0
    fi
    if app=$(find_app WezTerm); then
        open -n "$app" --args start -- "$BIN" && return 0
    fi
    if app=$(find_app Ghostty); then
        open -n "$app" --args -e "$BIN" && return 0
    fi
    if app=$(find_app iTerm); then
        /usr/bin/osascript - "$BIN" <<'OSA' && return 0
on run argv
    tell application "iTerm"
        activate
        create window with default profile command (item 1 of argv)
    end tell
end run
OSA
    fi
    return 1
}

if [[ "${TERMTUBE_LAUNCH_NOOPEN:-}" != 1 && "${TERMTUBE_TERMINAL:-}" != terminal ]]; then
    launch_graphics_terminal && exit 0
fi

if [[ "${TERMTUBE_LAUNCH_NOOPEN:-}" == 1 ]]; then
    tty="${TERMTUBE_LAUNCH_TTY:?}"
else
    tty=$(/usr/bin/osascript <<'OSA'
tell application "Terminal"
    activate
    set t to do script ""
    return tty of t
end tell
OSA
    ) || exit 1
fi
short="${tty#/dev/}"

# Processes on the window's tty, minus the `login` wrapper. Prints "<stat> <command>" lines.
tty_procs() {
    ps -t "$short" -o stat=,comm= 2>/dev/null | awk '{ n=$2; sub(".*/","",n); sub("^-","",n); if (n!="login") print $1, n }'
}

type_command() {
    local cmd="exec '$BIN'"
    /usr/bin/osascript - "$tty" "$cmd" <<'OSA'
on run argv
    tell application "Terminal"
        repeat with w in windows
            repeat with t in tabs of w
                if (tty of t) is (item 1 of argv) then
                    do script (item 2 of argv) in t
                    return
                end if
            end repeat
        end repeat
    end tell
end run
OSA
}

tmux_session_for_tty() {
    tmux list-clients -F '#{client_tty} #{session_name}' 2>/dev/null | awk -v t="$tty" '$1==t { print $2; exit }'
}

stable=0
last_session=
for ((i = 0; i < TIMEOUT_TICKS; i++)); do
    sleep 0.5
    procs=$(tty_procs)
    if grep -q ' tmux$' <<<"$procs"; then
        session=$(tmux_session_for_tty)
        if [[ -n "$session" ]]; then
            # The user's rc auto-attached tmux. Detach this window's client: an rc that merely runs
            # `tmux new-session` carries on to a plain prompt, where TermTube then runs outside tmux.
            last_session="$session"
            tmux detach-client -t "$tty" 2>/dev/null
            stable=0
        fi
        continue
    fi
    # An rc that `exec`s tmux ends the shell on detach: the window is gone, so use the session instead.
    if [[ -n "$last_session" && -z "$procs" ]]; then
        exec tmux new-window -t "$last_session:" -n TermTube "exec '$BIN'"
    fi
    # One process left on the tty that is not a multiplexer: the shell has finished its startup files.
    if [[ $(grep -c . <<<"$procs") -eq 1 ]]; then
        stable=$((stable + 1))
        if ((stable >= 3)); then
            type_command
            exit 0
        fi
    else
        stable=0
    fi
done

type_command
