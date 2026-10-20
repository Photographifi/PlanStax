"""Languages of PlanStax: French (the texts written in the code), English and Spanish.

User-visible texts are written in French and wrapped in tr(); the catalogues
planstax/locales/en.py and es.py map each French text to its translation, and a text missing
from a catalogue stays in French. Values are filled in by tr() itself:
tr("{n} images empilées", n=12).

The language is, in this order: the one given to set_language(), the PLANSTAX_LANG
variable, the choice saved from the Display menu, the language of the system — English for
a system in any other language.
"""

from __future__ import annotations

import importlib
import locale
import os
import re
import sys

LANGUAGES = {"fr": "Français", "en": "English", "es": "Español"}
FALLBACK = "en"

_current: str | None = None
_catalog: dict[str, str] = {}


def _code(name: str | None) -> str | None:
    """'fr_FR', 'es-ES', 'French_France', 'Spanish'… → 'fr' / 'es' / 'en', else None."""
    if not name:
        return None
    low = name.lower()
    for code, word in (("fr", "french"), ("es", "spanish"), ("en", "english")):
        if low.startswith(code) or low.startswith(word):
            return code
    return None


def system_language() -> str:
    if os.name == "nt":
        try:
            import ctypes
            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            return {0x0C: "fr", 0x0A: "es", 0x09: "en"}.get(primary, FALLBACK)
        except (AttributeError, OSError):
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        code = _code(os.environ.get(var, "").split(":")[0])
        if code:
            return code
    if sys.platform == "darwin":
        try:  # applications started from the Finder have no LANG
            import subprocess
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                                 text=True, timeout=5).stdout
            match = re.search(r'"?([a-zA-Z]{2})[-_"]', out)
            code = _code(match.group(1)) if match else None
            if code:
                return code
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:
        return _code(locale.getlocale()[0]) or FALLBACK
    except ValueError:
        return FALLBACK


def saved_language() -> str | None:
    """The language chosen in the Display menu (interface.ini), None for automatic."""
    from .settings import config_dir
    try:
        with open(os.path.join(config_dir(), "interface.ini"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = re.match(r"\s*language\s*=\s*(\w+)", line)
                if match and match.group(1) in LANGUAGES:
                    return match.group(1)
    except OSError:
        pass
    return None


def set_language(code: str | None = None) -> str:
    """Choose the language (None: automatic, see the module notes). Returns its code."""
    global _current, _catalog
    code = code or os.environ.get("PLANSTAX_LANG") or saved_language() or system_language()
    code = code if code in LANGUAGES else FALLBACK
    _catalog = {} if code == "fr" else importlib.import_module(f"planstax.locales.{code}").MESSAGES
    _current = code
    return code


def language() -> str:
    if _current is None:
        set_language()
    return _current


def N_(text: str) -> str:
    """Marks a text that is translated later, by tr(variable) (lists of labels…)."""
    return text


def tr(text: str, **values) -> str:
    """`text` (French) in the current language, with its {placeholders} filled in."""
    if _current is None:
        set_language()
    out = _catalog.get(text, text)
    return out.format(**values) if values else out


def megabytes(size: int) -> str:
    """A file size: « 24 Mo », « 24 MB »…"""
    mb = size / 2 ** 20
    return tr("{n} Mo", n=number(mb)) if mb >= 1 else tr("< 1 Mo")


def number(value: float, digits: int = 0) -> str:
    """A number as the current language writes it (decimal comma in French and Spanish)."""
    text = f"{value:,.{digits}f}"
    if language() == "en":
        return text
    # 12,345.6 → 12 345,6 (no-break space between thousands)
    return text.replace(",", " ").replace(".", ",")
