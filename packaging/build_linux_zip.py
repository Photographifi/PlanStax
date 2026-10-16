"""Build dist/PlanStax-<version>-Linux.zip: the sources plus a launcher script that installs the
libraries into a private environment on first run (see packaging/linux/).

    .venv\\Scripts\\python.exe packaging\\build_linux_zip.py
"""

from __future__ import annotations

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from planstax import __version__  # noqa: E402

TOP = "PlanStax"
FILES = ["LICENSE", "README.md", "pyproject.toml", "requirements.txt"]
EXECUTABLE = 0o100755 << 16   # rwxr-xr-x, honoured by unzip on Linux
REGULAR = 0o100644 << 16


def _lf(data: bytes) -> bytes:
    # Shell scripts break on CRLF line endings ("bash\r: not found"), and Git may check files
    # out with CRLF on Windows.
    return data.replace(b"\r\n", b"\n")


def _add(zf: zipfile.ZipFile, arcname: str, data: bytes, mode: int = REGULAR) -> None:
    info = zipfile.ZipInfo(f"{TOP}/{arcname}", date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3          # Unix, so that the permissions are applied
    info.external_attr = mode
    zf.writestr(info, data)


def build(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"PlanStax-{__version__}-Linux.zip")
    count = 0
    with zipfile.ZipFile(path, "w") as zf:
        for name in FILES:
            with open(os.path.join(ROOT, name), "rb") as fh:
                _add(zf, name, _lf(fh.read()))
            count += 1
        package = os.path.join(ROOT, "planstax")
        for d, dirs, files in os.walk(package):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for f in sorted(files):
                if f.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(d, f)
                rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
                with open(full, "rb") as fh:
                    data = fh.read()
                _add(zf, rel, _lf(data) if f.endswith(".py") else data)
                count += 1
        with open(os.path.join(HERE, "linux", "planstax.sh"), "rb") as fh:
            _add(zf, "planstax.sh", _lf(fh.read()), EXECUTABLE)
        with open(os.path.join(HERE, "linux", "LISEZ-MOI-Linux.txt"), encoding="utf-8") as fh:
            _add(zf, "LISEZ-MOI-Linux.txt", fh.read().replace("{version}", __version__).encode("utf-8"))
        count += 2
    print(f"archive : {path} ({count} fichiers, {os.path.getsize(path) / 1024:.0f} Ko)")
    return path


def main() -> int:
    build(os.path.join(ROOT, "dist"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
