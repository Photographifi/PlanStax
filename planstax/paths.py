"""Where PlanStax lives on disk (portable build or development folder)."""

from __future__ import annotations

import os
import sys


def is_portable() -> bool:
    """True when running as the portable build's PlanStax.exe."""
    return os.path.basename(sys.executable).lower().startswith("planstax")


def app_home() -> str:
    """The PlanStax folder: next to PlanStax.exe in the portable build, the project
    folder in a development checkout, otherwise Documents\\PlanStax."""
    if is_portable():
        return os.path.dirname(sys.executable)
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(os.path.join(project, "pyproject.toml")):
        return project
    return os.path.join(os.path.expanduser("~"), "Documents", "PlanStax")


def default_batch_folders() -> tuple[str, str]:
    """The "input" and "output" folders used by batch processing (created if needed). Falls
    back to Documents\\PlanStax when the program's folder is not writable."""
    for home in (app_home(), os.path.join(os.path.expanduser("~"), "Documents", "PlanStax")):
        folders = (os.path.join(home, "input"), os.path.join(home, "output"))
        try:
            for f in folders:
                os.makedirs(f, exist_ok=True)
            return folders
        except OSError:
            continue
    return folders
