# Creates PlanStax.lnk, which starts the program through the virtual environment's pythonw.exe
# (signed by the Python Software Foundation, so Windows 11 Smart App Control lets it run).
# Usage:  powershell -ExecutionPolicy Bypass -File packaging\make_shortcut.ps1 [-Destination <folder>]
param([string]$Destination = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$icon = Join-Path $root "planstax\resources\planstax.ico"
if (-not (Test-Path $icon)) {
    & (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $PSScriptRoot "make_icon.py") $icon
}
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $Destination "PlanStax.lnk"))
$lnk.TargetPath = Join-Path $root ".venv\Scripts\pythonw.exe"
$lnk.Arguments = "-m planstax"
$lnk.WorkingDirectory = $root
$lnk.IconLocation = "$icon,0"
$lnk.Description = "PlanStax - empilement et ondelettes planetaires"
$lnk.Save()
Write-Host "Raccourci créé : $(Join-Path $Destination 'PlanStax.lnk')"
