"""List the texts to translate: the literal first argument of every tr() and N_() call in the
planstax package (and the portable launcher), in order of appearance.

    .venv\\Scripts\\python.exe packaging\\extract_texts.py            # every text
    .venv\\Scripts\\python.exe packaging\\extract_texts.py --missing  # texts missing from a catalogue
"""

from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = [os.path.join(ROOT, "planstax"), os.path.join(ROOT, "packaging", "portable", "sitecustomize.py")]


def texts() -> list[tuple[str, str, int]]:
    """(text, file, line) of every translatable literal, first occurrence only."""
    found: dict[str, tuple[str, str, int]] = {}
    files = []
    for src in SOURCES:
        if os.path.isfile(src):
            files.append(src)
            continue
        for folder, _, names in os.walk(src):
            if "locales" in folder.split(os.sep):
                continue
            files += [os.path.join(folder, n) for n in names if n.endswith(".py")]
    for path in sorted(files):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), path)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                text = node.args[0].value
                if text not in found:
                    found[text] = (text, os.path.relpath(path, ROOT), node.lineno)
            elif (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id == "message" and isinstance(node.value, ast.Constant)
                  and isinstance(node.value.value, str) and path.endswith("sitecustomize.py")):
                found.setdefault(node.value.value, (node.value.value, os.path.relpath(path, ROOT), node.lineno))
    return sorted(found.values(), key=lambda t: (t[1], t[2]))


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    items = texts()
    if "--missing" in sys.argv:
        from planstax.locales import en, es
        for code, catalog in (("en", en.MESSAGES), ("es", es.MESSAGES)):
            for text, path, line in items:
                if text not in catalog:
                    print(f"[{code}] {path}:{line}: {text!r}")
    else:
        for text, path, line in items:
            print(f"{path}:{line}: {text!r}")
        print(len(items), "textes", file=sys.stderr)
