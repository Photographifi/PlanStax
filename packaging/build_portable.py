"""Build the portable Windows version: dist/PlanStax/ and dist/PlanStax-<version>-Windows.zip.

Nothing to install for the person receiving it: unzip, double-click PlanStax.exe.

PlanStax.exe is the Python Software Foundation's signed pythonw.exe, renamed (see
portable/sitecustomize.py): Windows SmartScreen and Smart App Control accept it, whereas a
launcher compiled here (PyInstaller…) would be unsigned and blocked on many PCs.

    .venv\\Scripts\\python.exe packaging\\build_portable.py
"""

from __future__ import annotations

import compileall
import os
import py_compile
import shutil
import struct
import sys
import sysconfig
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from planstax import __version__  # noqa: E402

DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(DIST, "PlanStax")
RUNTIME = os.path.join(OUT, "runtime")
SITE_OUT = os.path.join(RUNTIME, "site-packages")
BASE = sys.base_prefix
SITE_IN = sysconfig.get_paths()["purelib"]
PYDLL = f"python{sys.version_info.major}{sys.version_info.minor}.dll"

PACKAGES = ["numpy", "numpy.libs", "cv2", "PySide6", "shiboken6", "tifffile"]
DIST_INFOS = ("numpy-", "opencv_python_headless-", "pyside6_essentials-", "shiboken6-", "tifffile-")
STDLIB_SKIP = {"site-packages", "test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3",
               "venv", "__pycache__", "pydoc_data", "turtle.py"}
DLLS_SKIP = ("_tkinter.pyd", "tcl", "tk", "_test", "xxlimited")
# PySide6: Python modules and Qt plugins PlanStax actually uses; every Qt DLL they don't
# (transitively) need is dropped — that removes QML, Quick, Designer, WebView, software OpenGL…
QT_MODULES = {"qtcore.pyd", "qtgui.pyd", "qtwidgets.pyd"}
QT_PLUGINS = {"platforms", "styles", "imageformats", "iconengines"}
QT_DROP_DIRS = {"qml", "resources", "metatypes", "typesystems", "include", "scripts", "glue",
                "doc", "support", "examples", "designer"}
VC_RUNTIME = {"msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll",
              "msvcp140_codecvt_ids.dll", "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll",
              "vcomp140.dll"}
SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")


def log(msg: str) -> None:
    print(msg, flush=True)


def tree_size(path: str) -> int:
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs)


# ------------------------------------------------------------------ PE import scanning
def pe_imports(path: str) -> set[str]:
    """Names of the DLLs a PE file imports (normal and delay-load import tables)."""
    with open(path, "rb") as fh:
        data = fh.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return set()
    nsect, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    dirs = opt + (112 if struct.unpack_from("<H", data, opt)[0] == 0x20B else 96)
    sections = [struct.unpack_from("<IIII", data, opt + opt_size + 40 * i + 8) for i in range(nsect)]

    def offset(rva: int) -> int | None:
        for vsize, vaddr, rsize, rptr in sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return rva - vaddr + rptr
        return None

    def cstr(rva: int) -> str:
        o = offset(rva)
        return "" if o is None else data[o:data.index(b"\0", o)].decode("ascii", "replace")

    names: set[str] = set()
    for index, size, name_at in ((1, 20, 12), (13, 32, 4)):  # import table, delay-import table
        rva = struct.unpack_from("<I", data, dirs + 8 * index)[0]
        o = offset(rva) if rva else None
        while o is not None and o + size <= len(data):
            entry = data[o:o + size]
            if not any(entry):
                break
            n = cstr(struct.unpack_from("<I", entry, name_at)[0])
            if n:
                names.add(n.lower())
            o += size
    return names


def is_system_dll(name: str) -> bool:
    if name.startswith(("api-ms-win-", "ext-ms-")):
        return True
    return name not in VC_RUNTIME and os.path.isfile(os.path.join(SYSTEM32, name))


def binaries(folder: str):
    for d, _, files in os.walk(folder):
        for f in files:
            if f.lower().endswith((".dll", ".pyd", ".exe")):
                yield os.path.join(d, f)


# ------------------------------------------------------------------ copy steps
def copy_tree(src: str, dst: str, skip=lambda name: False) -> None:
    def ignore(_dir, names):
        return [n for n in names if n == "__pycache__" or skip(n)]
    shutil.copytree(src, dst, ignore=ignore)


def copy_python() -> None:
    log("• Python " + sys.version.split()[0])
    shutil.copy2(os.path.join(BASE, "pythonw.exe"), os.path.join(OUT, "PlanStax.exe"))
    for f in (PYDLL, "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        shutil.copy2(os.path.join(BASE, f), OUT)
    copy_tree(os.path.join(BASE, "Lib"), os.path.join(RUNTIME, "Lib"), lambda n: n in STDLIB_SKIP)
    copy_tree(os.path.join(BASE, "DLLs"), os.path.join(RUNTIME, "DLLs"),
              lambda n: n.lower().startswith(DLLS_SKIP))
    with open(os.path.join(OUT, "PlanStax._pth"), "w", encoding="ascii") as fh:
        fh.write("runtime\\Lib\nruntime\\DLLs\nruntime\\site-packages\nimport site\n")


def copy_packages() -> None:
    log("• bibliothèques : " + ", ".join(PACKAGES))
    for name in PACKAGES:
        src = os.path.join(SITE_IN, name)
        if os.path.isdir(src):
            copy_tree(src, os.path.join(SITE_OUT, name),
                      lambda n: n == "tests" or n.endswith(".pyi"))
    for entry in os.listdir(SITE_IN):
        if entry.lower().startswith(DIST_INFOS) and entry.endswith(".dist-info"):
            copy_tree(os.path.join(SITE_IN, entry), os.path.join(SITE_OUT, entry))
    shutil.rmtree(os.path.join(SITE_OUT, "cv2", "data"), ignore_errors=True)  # Haar cascades
    copy_tree(os.path.join(ROOT, "planstax"), os.path.join(SITE_OUT, "planstax"))
    shutil.copy2(os.path.join(HERE, "portable", "sitecustomize.py"), SITE_OUT)


def trim_pyside() -> None:
    qt = os.path.join(SITE_OUT, "PySide6")
    before = tree_size(qt)
    for d in QT_DROP_DIRS:
        shutil.rmtree(os.path.join(qt, d), ignore_errors=True)
    plugins = os.path.join(qt, "plugins")
    for d in os.listdir(plugins):
        if d not in QT_PLUGINS:
            shutil.rmtree(os.path.join(plugins, d))
    translations = os.path.join(qt, "translations")
    for f in os.listdir(translations):
        if not f.startswith("qtbase_"):
            os.remove(os.path.join(translations, f))
    for f in os.listdir(qt):
        if f.lower().endswith((".exe", ".pyd")) and f.lower() not in QT_MODULES:
            os.remove(os.path.join(qt, f))

    local = {f.lower(): os.path.join(qt, f) for f in os.listdir(qt) if f.lower().endswith(".dll")}
    # Plugins whose Qt libraries are not shipped in PySide6-Essentials (e.g. the PDF image
    # reader needs Qt6Pdf) could never load: drop them.
    for path in list(binaries(plugins)):
        if any(dep.startswith("qt6") and dep not in local for dep in pe_imports(path)):
            os.remove(path)

    # Keep only the Qt DLLs reachable from the kept modules and plugins.
    todo = [p for p in binaries(qt) if p.lower().endswith(".pyd") or p.startswith(plugins)]
    todo += [p for p in binaries(os.path.join(SITE_OUT, "shiboken6"))]
    needed: set[str] = set()
    while todo:
        for dep in pe_imports(todo.pop()):
            if dep in local and dep not in needed:
                needed.add(dep)
                todo.append(local[dep])
    for name, path in local.items():
        if name not in needed and name not in VC_RUNTIME:
            os.remove(path)
    log(f"• Qt allégé : {before / 2**20:.0f} Mo → {tree_size(qt) / 2**20:.0f} Mo")


def place_vc_runtime() -> None:
    """MSVC runtime DLLs next to PlanStax.exe, where every module finds them (PCs without
    the Visual C++ redistributable)."""
    for path in list(binaries(SITE_OUT)):
        name = os.path.basename(path).lower()
        if name in VC_RUNTIME and not os.path.exists(os.path.join(OUT, name)):
            shutil.copy2(path, os.path.join(OUT, name))


def check_dependencies() -> list[str]:
    """Every DLL imported by a bundled binary must be in the bundle or part of Windows."""
    available = {os.path.basename(p).lower() for p in binaries(OUT)}
    missing = set()
    for path in binaries(OUT):
        for dep in pe_imports(path):
            if dep not in available and not is_system_dll(dep):
                missing.add(f"{dep}  (requis par {os.path.relpath(path, OUT)})")
    for name in VC_RUNTIME:  # needed by someone but only present deep in a package folder?
        if name in available and not os.path.exists(os.path.join(OUT, name)):
            missing.add(f"{name}  (absent du dossier principal)")
    return sorted(missing)


def precompile() -> None:
    log("• précompilation Python")
    for folder in (os.path.join(RUNTIME, "Lib"), SITE_OUT):
        compileall.compile_dir(folder, quiet=1, workers=0,
                               invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)


def write_docs() -> None:
    with open(os.path.join(HERE, "portable", "LISEZ-MOI.txt"), encoding="utf-8") as fh:
        text = fh.read().replace("{version}", __version__)
    with open(os.path.join(OUT, "LISEZ-MOI.txt"), "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write(text)
    # Batch folders, ready to use (the note also keeps "input" from being an empty folder).
    os.makedirs(os.path.join(OUT, "output"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "input"), exist_ok=True)
    shutil.copy2(os.path.join(HERE, "portable", "input-LISEZ-MOI.txt"),
                 os.path.join(OUT, "input", "LISEZ-MOI.txt"))
    licences = os.path.join(RUNTIME, "licences")
    os.makedirs(licences, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "LICENSE"), os.path.join(licences, "PlanStax-LICENSE.txt"))
    shutil.copy2(os.path.join(BASE, "LICENSE.txt"), os.path.join(licences, "Python-LICENSE.txt"))


def make_zip() -> str:
    path = os.path.join(DIST, f"PlanStax-{__version__}-Windows.zip")
    if os.path.exists(path):
        os.remove(path)
    log("• compression")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for d, dirs, files in os.walk(OUT):
            if not dirs and not files:  # keep empty folders such as "output"
                zf.writestr(os.path.join("PlanStax", os.path.relpath(d, OUT)) + "/", "")
            for f in files:
                full = os.path.join(d, f)
                zf.write(full, os.path.join("PlanStax", os.path.relpath(full, OUT)))
    return path


def main() -> int:
    if os.name != "nt":
        log("La version portable se fabrique sous Windows.")
        return 1
    if os.path.isdir(OUT):
        # The previous build may be in use (a desktop shortcut to dist\PlanStax\PlanStax.exe):
        # never wipe videos or images someone put in its batch folders.
        own = [os.path.join(OUT, "input", "LISEZ-MOI.txt")]
        user_files = [os.path.join(d, f) for sub in ("input", "output")
                      for d, _, files in os.walk(os.path.join(OUT, sub)) for f in files
                      if os.path.join(d, f) not in own]
        if user_files:
            log("ARRÊT : la version portable précédente contient vos fichiers, qui seraient effacés :\n  "
                + "\n  ".join(user_files[:10]) + ("\n  …" if len(user_files) > 10 else "")
                + "\nDéplacez-les ailleurs, puis relancez.")
            return 3
        shutil.rmtree(OUT)
    os.makedirs(SITE_OUT)
    copy_python()
    copy_packages()
    trim_pyside()
    place_vc_runtime()
    missing = check_dependencies()
    if missing:
        log("DÉPENDANCES MANQUANTES :\n  " + "\n  ".join(missing))
        return 2
    log("• dépendances : toutes présentes")
    precompile()
    write_docs()
    log(f"• dossier : {OUT} ({tree_size(OUT) / 2**20:.0f} Mo)")
    z = make_zip()
    log(f"• archive : {z} ({os.path.getsize(z) / 2**20:.0f} Mo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
