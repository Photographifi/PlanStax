"""Desktop shortcut creation (Windows), for both the portable build and a development install."""

from __future__ import annotations

import os
import subprocess
import sys

from ..paths import app_home, is_portable

ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources",
                    "planstax.ico")

_SCRIPT = r"""
$desktop = [Environment]::GetFolderPath('Desktop')
$path = Join-Path $desktop 'PlanStax.lnk'
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$lnk.TargetPath = $env:PS_TARGET
$lnk.Arguments = $env:PS_ARGS
$lnk.WorkingDirectory = $env:PS_WORKDIR
if (Test-Path $env:PS_ICON) { $lnk.IconLocation = "$($env:PS_ICON),0" }
$lnk.Description = 'PlanStax - empilement et ondelettes planetaires'
$lnk.Save()
Write-Output $path
"""


def launch_command() -> tuple[str, str, str]:
    """(target, arguments, working directory) that start PlanStax without a console."""
    exe = sys.executable
    if is_portable():
        return exe, "", app_home()  # portable build: PlanStax.exe is the launcher
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return (pythonw if os.path.isfile(pythonw) else exe), "-m planstax", app_home()


def create_desktop_shortcut() -> str:
    """Create PlanStax.lnk on the user's desktop (OneDrive-redirected desktops included)."""
    target, args, workdir = launch_command()
    env = dict(os.environ, PS_TARGET=target, PS_ARGS=args, PS_WORKDIR=workdir, PS_ICON=ICON)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", _SCRIPT],
        env=env, capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "échec de la création du raccourci")
    return result.stdout.strip().splitlines()[-1]
