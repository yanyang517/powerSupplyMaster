<#
Build the Windows executable for powerSupplyMaster (PyInstaller, onedir).

Output: dist\powerSupplyMaster\powerSupplyMaster.exe
        dist\powerSupplyMaster\config\clients.json   bundled allow-list, build fails without it

Both runtime config files sit next to the exe, which is where they are looked up when
sys.frozen is set (see server/registry.py:clients_file_path and views/window_geometry.py).
--add-data is deliberately not used: in onedir mode it lands under _internal\, which does not
match that lookup rule.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
  powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1 -VerifyOnly
  (-VerifyOnly re-checks an existing artifact without rebuilding; needs no .venv.)
#>
[CmdletBinding()]
param(
    [string]$Name = 'powerSupplyMaster',
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'

$DistDir = Join-Path $RepoRoot 'dist'
$AppDir = Join-Path $DistDir $Name
$ConfigDir = Join-Path $AppDir 'config'
$WorkDir = Join-Path $RepoRoot 'build\pyinstaller'
$ConfigBackup = Join-Path $RepoRoot 'build\dist-config-backup'
$BundledRegistry = Join-Path $ConfigDir 'clients.json'
$SourceRegistry = Join-Path $RepoRoot 'config\clients.json'

# COLLECT wipes dist\<Name> and rebuilds it empty, and PowerShell's folder copy nests the source
# inside the destination when that destination already exists. Both restore paths therefore go
# through this merge-safe helper instead of a bare Copy-Item/Move-Item.
function Copy-TreeInto {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Destination
    )
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source '*') -Destination $Destination -Recurse -Force
}

# The app refuses to start without the registry, so an artifact without it is a dead exe:
# fail the build instead of shipping something that only appears to do nothing.
function Assert-BundledRegistry {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw @"
bundled client registry is missing: $Path

The frozen build looks the registry up at <exe folder>\config\clients.json
(server/registry.py: clients_file_path), and bootstrap_access() exits with code 2 when that
file is absent. In a --windowed build there is no console, so the user only sees a double-click
that does nothing. Seed it from $SourceRegistry (the build does this automatically).
"@
    }
    if ((Get-Item -LiteralPath $Path).Length -eq 0) {
        throw "bundled client registry is empty: $Path"
    }

    try {
        $document = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "bundled client registry is not valid JSON: $Path ($($_.Exception.Message))"
    }
    if (-not $document.PSObject.Properties['clients']) {
        throw "bundled client registry has no 'clients' object: $Path"
    }

    $count = @($document.clients.PSObject.Properties.Name).Count
    if ($count -eq 0) {
        Write-Warning "bundled client registry has no entries, every client will be denied: $Path"
    }
    Write-Host "Client registry bundled: $Path ($count entry(ies))"
}

if ($VerifyOnly) {
    Assert-BundledRegistry $BundledRegistry
    return
}

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

    if (-not (Test-Path -LiteralPath $SourceRegistry -PathType Leaf)) {
        throw "no client registry to bundle: $SourceRegistry (it is tracked in git, restore it)"
    }

    # COLLECT rewrites the whole app folder, so the saved window geometry and the registry the
    # app may have rewritten at runtime would otherwise be lost on every rebuild.
    if (Test-Path $ConfigDir) {
        if (Test-Path $ConfigBackup) { Remove-Item -Recurse -Force $ConfigBackup }
        Move-Item $ConfigDir $ConfigBackup
    }

    # Build-time provenance lives in a generated, gitignored module. Delete any stale copy
    # first: a leftover from an earlier commit would otherwise be collected and reported as
    # this build's origin.
    $BuildInfo = Join-Path $SrcPath '_build_info.py'
    Remove-Item -Force $BuildInfo -ErrorAction SilentlyContinue
    $Commit = ((& git -C $RepoRoot rev-parse --short HEAD) 2>$null | Out-String).Trim()
    if (-not $Commit) { $Commit = 'unknown' }
    $BuildTime = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    Set-Content -Path $BuildInfo -Encoding ascii -Value @(
        '"""Generated by scripts/build_exe.ps1 - do not edit or commit."""',
        "build_commit = '$Commit'",
        "build_time = '$BuildTime'"
    )

    # exe version metadata is derived from src/version.py. Fail the build rather than emit
    # an exe whose properties cannot tell us which version a user is running.
    $VersionResource = Join-Path $WorkDir 'version_info.txt'
    & $VenvPython (Join-Path $RepoRoot 'scripts\make_version_info.py') --out $VersionResource
    if ($LASTEXITCODE -ne 0) { throw "failed to generate version resource (exit $LASTEXITCODE)" }

    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --windowed `
        --name $Name `
        --paths $SrcPath `
        --hidden-import serial.asyncio `
        --hidden-import _build_info `
        --version-file $VersionResource `
        --distpath $DistDir `
        --workpath $WorkDir `
        --specpath $WorkDir `
        $Entry
    $PyiExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($PyiExit -ne 0) {
        # Merge back but keep the backup: this run failed, a retry still needs the data.
        if (Test-Path $ConfigBackup) { Copy-TreeInto $ConfigBackup $ConfigDir }
        throw "PyInstaller failed with exit code $PyiExit"
    }

    if (Test-Path $ConfigBackup) {
        Copy-TreeInto $ConfigBackup $ConfigDir
        Remove-Item -Recurse -Force $ConfigBackup
    }

    # Seed only when the artifact has no registry at all, so a runtime-edited allow-list
    # restored just above is never clobbered by a rebuild.
    if (-not (Test-Path -LiteralPath $BundledRegistry -PathType Leaf)) {
        New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
        Copy-Item -LiteralPath $SourceRegistry -Destination $BundledRegistry -Force
        Write-Host "Seeded $BundledRegistry from $SourceRegistry"
    }
    else {
        Write-Host "Kept existing runtime registry: $BundledRegistry"
    }

    $Exe = Join-Path $AppDir "$Name.exe"
    if (-not (Test-Path $Exe)) { throw "expected artifact is missing: $Exe" }
    Assert-BundledRegistry $BundledRegistry

    $SizeMb = [math]::Round((Get-ChildItem -Recurse $AppDir | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host ''
    Write-Host "Built $Exe ($SizeMb MB in $AppDir)"
    Write-Host "Window geometry is stored in $(Join-Path $ConfigDir 'window_geometry.json')."
}
finally {
    Pop-Location
}
