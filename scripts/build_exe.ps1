<#
Build the Windows executable for powerSupplyMaster (PyInstaller, onedir).

Output: dist\powerSupplyMaster\powerSupplyMaster.exe
The runtime config file is created next to the exe (see views/window_geometry.py).

Usage:
  powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
#>
[CmdletBinding()]
param(
    [string]$Name = 'powerSupplyMaster'
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    throw "venv not found at .venv. Create it first: python -m venv .venv ; .venv\Scripts\python.exe -m pip install -r requirements.txt"
}

Push-Location $RepoRoot
try {
    # PyInstaller and pip narrate on stderr, which 'Stop' would turn into a terminating
    # NativeCommandError; failures are detected via $LASTEXITCODE instead.
    $ErrorActionPreference = 'Continue'

    # PyInstaller is a build-only tool on purpose: it stays out of requirements.txt.
    & $VenvPython -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing PyInstaller into .venv (build-only dependency)...'
        & $VenvPython -m pip install --quiet pyinstaller
        if ($LASTEXITCODE -ne 0) { throw 'failed to install PyInstaller' }
    }

    $Entry = Join-Path $RepoRoot 'src\app.py'
    $SrcPath = Join-Path $RepoRoot 'src'
    $DistDir = Join-Path $RepoRoot 'dist'
    $WorkDir = Join-Path $RepoRoot 'build\pyinstaller'
    $AppDir = Join-Path $DistDir $Name
    $ConfigDir = Join-Path $AppDir 'config'
    $ConfigBackup = Join-Path $RepoRoot 'build\dist-config-backup'

    # COLLECT rewrites the whole app folder, so the saved window geometry of a previous
    # run would otherwise be lost on every rebuild.
    if (Test-Path $ConfigDir) {
        if (Test-Path $ConfigBackup) { Remove-Item -Recurse -Force $ConfigBackup }
        Move-Item $ConfigDir $ConfigBackup
    }

    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --windowed `
        --name $Name `
        --paths $SrcPath `
        --hidden-import serial.asyncio `
        --distpath $DistDir `
        --workpath $WorkDir `
        --specpath $WorkDir `
        $Entry
    $PyiExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($PyiExit -ne 0) {
        if (Test-Path $ConfigBackup) { Move-Item $ConfigBackup $ConfigDir -Force }
        throw "PyInstaller failed with exit code $PyiExit"
    }

    if (Test-Path $ConfigBackup) {
        Copy-Item -Recurse -Force $ConfigBackup $ConfigDir
        Remove-Item -Recurse -Force $ConfigBackup
    }

    $Exe = Join-Path $AppDir "$Name.exe"
    if (-not (Test-Path $Exe)) { throw "expected artifact is missing: $Exe" }

    $SizeMb = [math]::Round((Get-ChildItem -Recurse $AppDir | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host ''
    Write-Host "Built $Exe ($SizeMb MB in $AppDir)"
    Write-Host "Window geometry is stored in $(Join-Path $ConfigDir 'window_geometry.json')."
}
finally {
    Pop-Location
}
