"""Textos en español."""

from .catalog import TRANSLATIONS

MESSAGES = {fr: texts[1] for fr, texts in TRANSLATIONS.items()}
