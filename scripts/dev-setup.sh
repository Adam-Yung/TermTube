#!/usr/bin/env bash
# Development environment for this checkout: the repo's own .venv, kept separate from the installed app's venv
# (~/.local/share/TermTube/.venv). Always acts through .venv/bin/python, never a bare `pip`.
#
#   scripts/dev-setup.sh --check       report only, changes nothing (default)
#   scripts/dev-setup.sh --install     create .venv if missing, then pip install -r requirements-dev.txt
#   scripts/dev-setup.sh --recreate    delete .venv and build it again (asks first; --yes skips the question)
#
# --install and --recreate download packages from PyPI. --check never touches the network.
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
APP_DIR="${TERMTUBE_APP_DIR:-$HOME/.local/share/TermTube}"
PYTHON="${PYTHON:-python3}"

mode="check"
assume_yes=false
for arg in "$@"; do
    case "$arg" in
        --check) mode="check" ;;
        --install) mode="install" ;;
        --recreate) mode="recreate" ;;
        --yes|-y) assume_yes=true ;;
        -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

problems=0
ok()   { echo "  ok    $*"; }
warn() { echo "  WARN  $*"; }
bad()  { echo "  FAIL  $*"; problems=$((problems + 1)); }
real() { (cd -P "$1" 2>/dev/null && pwd) || echo "$1"; }

check() {
    echo "Repo:        $ROOT"
    echo "Dev venv:    $VENV"
    echo "App install: $APP_DIR (venv $APP_DIR/.venv)"
    echo
    if [[ ! -x "$VENV/bin/python" ]]; then
        bad "no dev venv: run scripts/dev-setup.sh --install"
        return
    fi

    if [[ -L "$VENV" ]]; then
        bad ".venv is a symlink to $(readlink "$VENV"): dev and app environments would be shared"
    else
        ok ".venv is a real directory"
    fi

    local prefix
    prefix="$("$VENV/bin/python" -c 'import sys; print(sys.prefix)')"
    if [[ "$(real "$prefix")" == "$(real "$VENV")" ]]; then
        ok "its python runs with prefix $prefix"
    else
        bad ".venv/bin/python has prefix $prefix, not this repo's .venv"
    fi

    if [[ -d "$APP_DIR/.venv" ]]; then
        if [[ "$(real "$APP_DIR/.venv")" == "$(real "$VENV")" ]]; then
            bad "the app venv and the dev venv are the same directory"
        else
            ok "the app venv is a different directory"
        fi
        local shared
        shared="$(find "$VENV" -maxdepth 4 -type l ! -path "$VENV/bin/python*" -lname "$APP_DIR/*" 2>/dev/null || true)"
        if [[ -n "$shared" ]]; then
            bad "links from the dev venv into the app install:"
            echo "$shared" | sed 's/^/          /'
        else
            ok "no links from the dev venv into the app install"
        fi
    else
        ok "no app install found (nothing to clash with)"
    fi

    local shebang
    shebang="$(head -1 "$VENV/bin/pip" 2>/dev/null | sed 's/^#!//' || true)"
    if [[ -z "$shebang" ]]; then
        warn "pip is missing from the dev venv"
    elif [[ "$shebang" == "$VENV/bin/python"* ]]; then
        ok "pip belongs to the dev venv"
    else
        bad "pip in the dev venv runs $shebang (a copied venv); use --recreate"
    fi

    local created
    created="$(sed -n 's/^command = .* -m venv //p' "$VENV/pyvenv.cfg" 2>/dev/null || true)"
    if [[ -n "$created" && "$(real "$created" 2>/dev/null)" != "$(real "$VENV")" ]]; then
        warn "pyvenv.cfg says this venv was created for $created (copied from elsewhere); --recreate makes it clean"
    fi

    if "$VENV/bin/python" -c 'import ruff' 2>/dev/null || [[ -x "$VENV/bin/ruff" ]]; then
        ok "ruff is installed in the dev venv"
    else
        warn "ruff is not in the dev venv: run scripts/dev-setup.sh --install"
    fi
    if "$VENV/bin/python" -c 'import pytest, textual, yt_dlp' 2>/dev/null; then
        ok "pytest, textual and yt_dlp import"
    else
        warn "requirements are not all installed: run scripts/dev-setup.sh --install"
    fi
}

install() {
    if [[ ! -x "$VENV/bin/python" ]]; then
        echo "Creating $VENV with $PYTHON"
        "$PYTHON" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
        "$PYTHON" -m venv "$VENV"
    fi
    "$VENV/bin/python" -m pip install -r "$ROOT/requirements-dev.txt"
}

recreate() {
    if [[ "$VENV" != "$ROOT/.venv" || "$(real "$VENV")" == "$(real "$APP_DIR/.venv")" ]]; then
        echo "refusing: $VENV is not a separate dev venv" >&2
        exit 1
    fi
    if [[ "$assume_yes" != true ]]; then
        read -r -p "Delete $VENV and build it again? [y/N] " reply
        [[ "$reply" =~ ^[Yy]$ ]] || { echo "cancelled"; exit 0; }
    fi
    if [[ -L "$VENV" ]]; then rm "$VENV"; else rm -rf "$VENV"; fi
    install
}

case "$mode" in
    check) check ;;
    install) install; echo; check ;;
    recreate) recreate; echo; check ;;
esac

echo
if [[ $problems -gt 0 ]]; then
    echo "$problems problem(s). See above."
    exit 1
fi
echo "Dev environment OK. Gate: scripts/verify.sh"
