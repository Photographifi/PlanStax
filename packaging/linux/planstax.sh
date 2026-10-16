#!/usr/bin/env bash
# PlanStax for Linux.
# First run: creates a private Python environment in .venv next to this script and downloads
# the libraries into it (about 150 MB, once). Then starts PlanStax. Arguments are passed on:
#   ./planstax.sh                       interface
#   ./planstax.sh video.ser             interface, opening a video
#   ./planstax.sh batch input output    command line (see LISEZ-MOI-Linux.txt)
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/.venv"
python="${PYTHON:-python3}"

fail() {
    echo "PlanStax : $1" >&2
    echo "Voir LISEZ-MOI-Linux.txt." >&2
    exit 1
}

if [ ! -x "$venv/bin/python" ] || [ ! -f "$venv/.planstax-ok" ]; then
    command -v "$python" >/dev/null 2>&1 || fail "python3 est introuvable : installez-le."
    "$python" -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
        || fail "Python 3.10 ou plus récent est nécessaire ($("$python" --version 2>&1))."
    echo "Premier lancement : installation des bibliothèques (environ 150 Mo, une seule fois)…"
    rm -rf "$venv"
    "$python" -m venv "$venv" \
        || fail "impossible de créer l'environnement Python (paquet python3-venv manquant ?)."
    "$venv/bin/python" -m pip install --upgrade --quiet pip \
        && "$venv/bin/python" -m pip install --quiet -r "$here/requirements.txt" \
        || { rm -rf "$venv"; fail "l'installation des bibliothèques a échoué (connexion Internet ?)."; }
    touch "$venv/.planstax-ok"
    echo "Installation terminée."
fi

# Qt 6 needs libxcb-cursor to open a window under X11 / XWayland: warn early if it is missing.
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -n "${DISPLAY:-}" ]; then
    libs="$(ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null || /usr/sbin/ldconfig -p 2>/dev/null)"
    if [ -n "$libs" ] && ! printf '%s' "$libs" | grep -q "libxcb-cursor.so.0"; then
        echo "Attention : la bibliothèque libxcb-cursor semble absente ; si la fenêtre ne s'ouvre pas," >&2
        echo "installez-la (Ubuntu/Debian : sudo apt install libxcb-cursor0)." >&2
    fi
fi

export PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}"
exec "$venv/bin/python" -m planstax "$@"
