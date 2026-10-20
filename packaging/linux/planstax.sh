#!/usr/bin/env bash
# PlanStax for Linux.
# First run: creates a private Python environment in .venv next to this script and downloads
# the libraries into it (about 150 MB, once). Then starts PlanStax. Arguments are passed on:
#   ./planstax.sh                       interface
#   ./planstax.sh video.ser             interface, opening a video
#   ./planstax.sh batch input output    command line (see README-Linux.txt)
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv="$here/.venv"
python="${PYTHON:-python3}"

case "${PLANSTAX_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in
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
    say "Voir LISEZ-MOI-Linux.txt." "See README-Linux.txt." "Véase LEAME-Linux.txt." >&2
    exit 1
}

if [ ! -x "$venv/bin/python" ] || [ ! -f "$venv/.planstax-ok" ]; then
    command -v "$python" >/dev/null 2>&1 || fail "python3 est introuvable : installez-le." \
        "python3 cannot be found: please install it." "no se encuentra python3: instálelo."
    version="$("$python" --version 2>&1)"
    "$python" -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
        || fail "Python 3.10 ou plus récent est nécessaire ($version)." \
                "Python 3.10 or newer is needed ($version)." "se necesita Python 3.10 o más reciente ($version)."
    say "Premier lancement : installation des bibliothèques (environ 150 Mo, une seule fois)…" \
        "First start: installing the libraries (about 150 MB, only once)…" \
        "Primer inicio: instalación de las bibliotecas (unos 150 MB, una sola vez)…"
    rm -rf "$venv"
    "$python" -m venv "$venv" \
        || fail "impossible de créer l'environnement Python (paquet python3-venv manquant ?)." \
                "cannot create the Python environment (python3-venv package missing?)." \
                "no se puede crear el entorno de Python (¿falta el paquete python3-venv?)."
    "$venv/bin/python" -m pip install --upgrade --quiet pip \
        && "$venv/bin/python" -m pip install --quiet -r "$here/requirements.txt" \
        || { rm -rf "$venv"; fail "l'installation des bibliothèques a échoué (connexion Internet ?)." \
                                  "the installation of the libraries failed (Internet connection?)." \
                                  "la instalación de las bibliotecas ha fallado (¿conexión a Internet?)."; }
    touch "$venv/.planstax-ok"
    say "Installation terminée." "Installation done." "Instalación terminada."
fi

# Qt 6 needs libxcb-cursor to open a window under X11 / XWayland: warn early if it is missing.
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -n "${DISPLAY:-}" ]; then
    libs="$(ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null || /usr/sbin/ldconfig -p 2>/dev/null)"
    if [ -n "$libs" ] && ! printf '%s' "$libs" | grep -q "libxcb-cursor.so.0"; then
        say "Attention : la bibliothèque libxcb-cursor semble absente ; si la fenêtre ne s'ouvre pas," \
            "Warning: the libxcb-cursor library seems missing; if the window does not open," \
            "Atención: la biblioteca libxcb-cursor parece ausente; si la ventana no se abre," >&2
        say "installez-la (Ubuntu/Debian : sudo apt install libxcb-cursor0)." \
            "install it (Ubuntu/Debian: sudo apt install libxcb-cursor0)." \
            "instálela (Ubuntu/Debian: sudo apt install libxcb-cursor0)." >&2
    fi
fi

export PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}"
exec "$venv/bin/python" -m planstax "$@"
