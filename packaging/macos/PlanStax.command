#!/bin/bash
# PlanStax for macOS. Double-click (or run in Terminal: bash PlanStax.command).
# First run: creates a private Python environment in .venv next to this script and downloads
# the libraries into it (about 150 MB, once). Then starts PlanStax. Arguments are passed on.
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/.venv"

lang="${PLANSTAX_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}"
if [ -z "$lang" ]; then  # started from the Finder without the Terminal's locale variables
    lang="$(defaults read -g AppleLanguages 2>/dev/null | tr -d ' "()\n,' | cut -c1-2)"
fi
case "$lang" in
    fr*) lang=fr ;;
    es*) lang=es ;;
    *) lang=en ;;
esac

say() {  # say "français" "English" "español"
    case "$lang" in
        fr) printf '%s\n' "$1" ;;
        es) printf '%s\n' "$3" ;;
        *) printf '%s\n' "$2" ;;
    esac
}

fail() {
    echo "PlanStax: $(say "$1" "$2" "$3")" >&2
    say "Voir LISEZ-MOI-Mac.txt." "See README-Mac.txt." "Véase LEAME-Mac.txt." >&2
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
    python="$(find_python)" \
        || fail "Python 3.10 ou plus récent est introuvable : installez Python 3.13 depuis https://www.python.org/downloads/macos/" \
                "Python 3.10 or newer cannot be found: install Python 3.13 from https://www.python.org/downloads/macos/" \
                "No se encuentra Python 3.10 o más reciente: instale Python 3.13 desde https://www.python.org/downloads/macos/"
    version="$("$python" --version)"
    say "Premier lancement : installation des bibliothèques avec $version (environ 150 Mo, une seule fois)…" \
        "First start: installing the libraries with $version (about 150 MB, only once)…" \
        "Primer inicio: instalación de las bibliotecas con $version (unos 150 MB, una sola vez)…"
    rm -rf "$venv"
    "$python" -m venv "$venv" || fail "impossible de créer l'environnement Python." \
        "cannot create the Python environment." "no se puede crear el entorno de Python."
    "$venv/bin/python" -m pip install --upgrade --quiet pip \
        && "$venv/bin/python" -m pip install --quiet -r "$here/requirements.txt" \
        || { rm -rf "$venv"; fail "l'installation des bibliothèques a échoué (connexion Internet ?)." \
                                  "the installation of the libraries failed (Internet connection?)." \
                                  "la instalación de las bibliotecas ha fallado (¿conexión a Internet?)."; }
    touch "$venv/.planstax-ok"
    say "Installation terminée." "Installation done." "Instalación terminada."
fi

export PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}"
exec "$venv/bin/python" -m planstax "$@"
