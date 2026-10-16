#!/bin/bash
# PlanStax for macOS. Double-click (or run in Terminal: bash PlanStax.command).
# First run: creates a private Python environment in .venv next to this script and downloads
# the libraries into it (about 150 MB, once). Then starts PlanStax. Arguments are passed on.
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/.venv"

fail() {
    echo "PlanStax : $1" >&2
    echo "Voir LISEZ-MOI-Mac.txt." >&2
    exit 1
}

# Downloaded files are quarantined by Gatekeeper; once this script runs, lift the quarantine
# on its own folder so the next double-click opens directly.
xattr -dr com.apple.quarantine "$here" 2>/dev/null || true

find_python() {
    # /usr/bin/python3 is Apple's 3.9 (too old) or, without the developer tools, a stub that
    # opens an installation dialog: try the python.org and Homebrew interpreters first.
    local candidates=()
    [ -n "${PYTHON:-}" ] && candidates+=("$PYTHON")
    for v in 3.13 3.12 3.14 3.11 3.10; do
        candidates+=("/Library/Frameworks/Python.framework/Versions/$v/bin/python$v")
        candidates+=("/opt/homebrew/bin/python$v" "/usr/local/bin/python$v")
    done
    candidates+=("/opt/homebrew/bin/python3" "/usr/local/bin/python3")
    for p in "${candidates[@]}"; do
        if [ -x "$p" ] && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

if [ ! -x "$venv/bin/python" ] || [ ! -f "$venv/.planstax-ok" ]; then
    python="$(find_python)" || fail "Python 3.10 ou plus récent est introuvable : installez Python 3.13 depuis https://www.python.org/downloads/macos/"
    echo "Premier lancement : installation des bibliothèques avec $("$python" --version) (environ 150 Mo, une seule fois)…"
    rm -rf "$venv"
    "$python" -m venv "$venv" || fail "impossible de créer l'environnement Python."
    "$venv/bin/python" -m pip install --upgrade --quiet pip \
        && "$venv/bin/python" -m pip install --quiet -r "$here/requirements.txt" \
        || { rm -rf "$venv"; fail "l'installation des bibliothèques a échoué (connexion Internet ?)."; }
    touch "$venv/.planstax-ok"
    echo "Installation terminée."
fi

export PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}"
exec "$venv/bin/python" -m planstax "$@"
