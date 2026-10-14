# Checks the portable zip the way a friend would use it: downloaded from the Internet (Mark of
# the Web), unzipped with Windows' own "Extract all", in a folder with spaces and accents.
# Then runs a full stacking through PlanStax.exe and starts the interface (off-screen).
# Usage:  powershell -ExecutionPolicy Bypass -File packaging\test_portable.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$zipSrc = Get-ChildItem (Join-Path $root "dist") -Filter "PlanStax-*-Windows.zip" | Select-Object -First 1
if (-not $zipSrc) { throw "Archive absente : lancez d'abord packaging\build_portable.py" }

$t = Join-Path $env:TEMP ("Test PlanStax été " + (Get-Date -Format "HHmmss"))
New-Item -ItemType Directory -Force $t | Out-Null
$zip = Join-Path $t $zipSrc.Name
Copy-Item $zipSrc.FullName $zip
Set-Content -Path $zip -Stream Zone.Identifier -Value "[ZoneTransfer]`r`nZoneId=3"

# Explorer's zip extraction (propagates the Internet mark to every file).
$sh = New-Object -ComObject Shell.Application
$sh.NameSpace($t).CopyHere($sh.NameSpace($zip).Items(), 20)
$app = Join-Path $t "PlanStax"
$expected = (Get-ChildItem (Join-Path $root "dist\PlanStax") -Recurse -File).Count
for ($i = 0; $i -lt 300; $i++) {
    Start-Sleep -Seconds 1
    if ((Get-ChildItem $app -Recurse -File -ErrorAction SilentlyContinue).Count -ge $expected) { break }
}
$exe = Join-Path $app "PlanStax.exe"
Write-Host "Extraction : $((Get-ChildItem $app -Recurse -File).Count)/$expected fichiers, marque Internet : $([bool](Get-Item $exe -Stream Zone.Identifier -ErrorAction SilentlyContinue))"

$env:APPDATA = Join-Path $t "appdata"
$demo = Join-Path $t "démo jupiter.ser"
& (Join-Path $root ".venv\Scripts\python.exe") -m planstax demo $demo --color --frames 80 | Out-Null

# 1. Full processing through the bundled program.
$out = Join-Path $t "résultats"
$p = Start-Process -FilePath $exe -PassThru -ArgumentList @("cli", "stack", "`"$demo`"", "-o", "`"$out`"", "--wavelets")
if (-not $p.WaitForExit(300000)) { Stop-Process -Id $p.Id -Force; throw "Empilement : pas de fin après 5 min" }
$files = @(Get-ChildItem $out -ErrorAction SilentlyContinue)
Write-Host "Empilement : code $($p.ExitCode), fichiers produits : $($files.Name -join ', ')"
if ($p.ExitCode -ne 0 -or $files.Count -ne 2) { throw "Empilement en échec" }

# 2. Batch with the default folders next to PlanStax.exe ("input" → "output").
Copy-Item $demo (Join-Path $app "input")
$b = Start-Process -FilePath $exe -PassThru -ArgumentList @("cli", "batch")
if (-not $b.WaitForExit(300000)) { Stop-Process -Id $b.Id -Force; throw "Lot : pas de fin après 5 min" }
$images = @(Get-ChildItem (Join-Path $app "output") -File)
Write-Host "Lot : code $($b.ExitCode), images dans output : $($images.Name -join ', ')"
if ($b.ExitCode -ne 0 -or $images.Count -ne 1) { throw "Traitement par lot en échec" }

# 3. Interface: must still be running after 10 s (no start-up error).
$env:QT_QPA_PLATFORM = "offscreen"
$g = Start-Process -FilePath $exe -PassThru -ArgumentList @("`"$demo`"")
Start-Sleep -Seconds 10
Remove-Item Env:QT_QPA_PLATFORM
if ($g.HasExited) { throw "Interface arrêtée (code $($g.ExitCode))" }
Stop-Process -Id $g.Id -Force
$err = Join-Path $env:APPDATA "PlanStax\erreur-demarrage.txt"
if (Test-Path $err) { Get-Content $err; throw "Erreur de démarrage enregistrée" }
Write-Host "Interface : démarrée sans erreur"
Write-Host "TOUT EST BON. Dossier de test : $t"
