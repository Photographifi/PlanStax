"""Start-up hook of the portable build.

PlanStax.exe is the Python Software Foundation's signed pythonw.exe, merely renamed, so
Windows (SmartScreen, Smart App Control) trusts it; a freshly compiled launcher would be
blocked as unsigned. Python imports this module while starting up: when the interpreter was
launched as PlanStax.exe, it runs the application, then ends the process (there is no
script for Python to run afterwards — a file passed on the command line, e.g. a .ser dropped
on the icon, is for PlanStax, not a Python script).

    PlanStax.exe [fichiers…]          interface graphique
    PlanStax.exe cli stack …          ligne de commande (sans console : voir le code retour)

("cli" is a plain word, not "--cli": Python rejects unknown dash options itself, before this
module runs, whereas a first plain argument is taken as a script name and only opened later.)
"""

import os
import sys


def _report(exc: BaseException) -> None:
    import traceback
    text = "".join(traceback.format_exception(exc))
    log = os.path.join(os.environ.get("APPDATA", os.path.dirname(sys.executable)), "PlanStax",
                       "erreur-demarrage.txt")
    try:
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        log = "(impossible d'écrire le journal)"
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, f"PlanStax n'a pas pu démarrer :\n\n{exc}\n\nDétails enregistrés dans :\n{log}",
            "PlanStax", 0x10)
    except Exception:  # noqa: BLE001
        pass


def _launch() -> None:
    argv = list(getattr(sys, "orig_argv", None) or [sys.executable] + sys.argv)
    if not os.path.basename(argv[0]).lower().startswith("planstax"):
        return  # plain python use of this runtime
    args = argv[1:]
    code = 0
    try:
        if args and args[0].lower() == "cli":
            from planstax.cli import main as cli_main
            code = cli_main(args[1:])
        else:
            from planstax.gui.app import main as gui_main
            code = gui_main([argv[0]] + args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    except BaseException as exc:  # noqa: BLE001
        _report(exc)
        code = 1
    os._exit(int(code or 0))


_launch()
