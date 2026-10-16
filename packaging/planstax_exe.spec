# PyInstaller spec: a single self-contained dist\exe\PlanStax-autonome.exe.
#
# Experimental. The file is not code-signed, so Windows 11 Smart App Control blocks it and
# SmartScreen warns about it on other PCs. The build to share is the portable one
# (packaging\build_portable.py), whose launcher is the signed pythonw.exe.
#
#   .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath dist\exe
#       --workpath packaging\build\pyi packaging\planstax_exe.spec
import os

HERE = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(HERE)
ICON = os.path.join(ROOT, "planstax", "resources", "planstax.ico")

a = Analysis(
    [os.path.join(HERE, "launch_exe.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "planstax", "resources"), os.path.join("planstax", "resources"))],
    excludes=["tkinter", "scipy", "matplotlib", "pytest", "IPython", "PySide6.QtNetwork",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSql", "PySide6.QtTest",
              "PySide6.QtOpenGL", "PySide6.QtPdf", "PySide6.QtMultimedia"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="PlanStax-autonome", console=False,
          icon=ICON, version=os.path.join(HERE, "version_info.txt"), upx=False)
