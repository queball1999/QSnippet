<#
Build the QSnippet-branded updater locally, the way CI does.

CI builds updater.exe in .github/workflows/build_updater.yaml and hands it to
the packaging job as an artifact. Nothing in a local build did that, so
QSnippet.iss (which requires output\windows\updater.exe) aborted the compile.
This script fills that gap: it builds the same binary from a QUpdateTool
checkout on this machine.

The result is NOT the binary that ships. CI pins QUpdateTool to a tag; a local
checkout is whatever you have. Use this for local install testing only.

  .\tools\build_updater.ps1                  # build if missing
  .\tools\build_updater.ps1 -Force           # always rebuild
  .\tools\build_updater.ps1 -QUpdateToolPath P:\Coding\Github Repos\QUpdateTool2.0

Writes output\windows\updater.exe and prints its SHA-256, which the caller
passes to build.ps1 as $env:UPDATER_SHA256 so build_info.py carries the same
stamp a CI build would.
#>
param(
    [string]$QUpdateToolPath = $env:QUPDATETOOL_DIR,
    [switch]$Force,
    # Matches the CI default; QSnippet launches the updater with --gui.
    [bool]$Gui = $true
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

$DistDir = Join-Path $RepoRoot "output\windows"
$Target  = Join-Path $DistDir "updater.exe"

# Hashed through .NET rather than Get-FileHash: that cmdlet is autoloaded
# from Microsoft.PowerShell.Utility, and invoking powershell.exe from make
# under Git Bash can hand it a mangled PSModulePath, at which point the
# cmdlet simply does not resolve. This has no such dependency.
function Get-Sha256($path) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $stream = [System.IO.File]::OpenRead((Resolve-Path $path).Path)
        try {
            return ([System.BitConverter]::ToString($sha.ComputeHash($stream))
                    ).Replace("-", "").ToLower()
        } finally {
            $stream.Dispose()
        }
    } finally {
        $sha.Dispose()
    }
}

function Write-Sha256($path) {
    $hash = Get-Sha256 $path
    Write-Host "Updater SHA-256: $hash" -ForegroundColor Cyan
    return $hash
}

if ((Test-Path $Target) -and -not $Force) {
    Write-Host "Updater already present: $Target (use -Force to rebuild)" -ForegroundColor DarkGray
    return Write-Sha256 $Target
}

# Locate a QUpdateTool checkout. Explicit path wins, then QUPDATETOOL_DIR,
# then the usual siblings of this repo.
if (-not $QUpdateToolPath) {
    $parent = Split-Path -Parent $RepoRoot
    foreach ($name in @("QUpdateTool2.0", "QUpdateTool")) {
        $candidate = Join-Path $parent $name
        if (Test-Path (Join-Path $candidate "tools\build_branded.py")) {
            $QUpdateToolPath = $candidate
            break
        }
    }
}

if (-not $QUpdateToolPath -or -not (Test-Path (Join-Path $QUpdateToolPath "tools\build_branded.py"))) {
    Write-Error @"
No QUpdateTool checkout found.

Clone it next to this repo, or point at it explicitly:
    git clone https://github.com/queball1999/QUpdateTool.git ..\QUpdateTool
    .\tools\build_updater.ps1 -QUpdateToolPath <path>
    (or set the QUPDATETOOL_DIR environment variable)
"@
}

$QUpdateToolPath = (Resolve-Path $QUpdateToolPath).Path
Write-Host "Building branded updater from $QUpdateToolPath" -ForegroundColor Cyan

$requirements = if ($Gui) { "requirements-gui.txt" } else { "requirements.txt" }
& python -m pip install -q -r (Join-Path $QUpdateToolPath $requirements)
if ($LASTEXITCODE -ne 0) { Write-Error "Failed installing updater dependencies" }

New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

$buildArgs = @(
    (Join-Path $QUpdateToolPath "tools\build_branded.py"),
    "--brand", (Join-Path $RepoRoot "config\updater.yaml"),
    "--icon",  (Join-Path $RepoRoot "assets\icons\QSnippet.ico"),
    "--key",   (Join-Path $RepoRoot "gpg-public.asc"),
    "--name",  "updater",
    "--out",   $Target,
    "--clean"
)
if ($Gui) { $buildArgs += "--gui" }

Push-Location $QUpdateToolPath
try {
    & python @buildArgs
    if ($LASTEXITCODE -ne 0) { Write-Error "Branded updater build failed" }
} finally {
    Pop-Location
}

if (-not (Test-Path $Target)) {
    Write-Error "Build reported success but $Target is missing"
}

# Same smoke test CI runs: exit 10 (update available) or 11 (up to date)
# proves the brand, pinned key, and release backend all resolved. Any other
# code is a warning, not a failure: offline or rate-limited is common on a
# dev machine and says nothing about the binary.
$smoke = & $Target --check-only --current-version 0.0.0 --log-file none 2>&1
$code = $LASTEXITCODE
if ($code -ne 10 -and $code -ne 11) {
    Write-Warning "updater --check-only exited with $code; the binary may be misconfigured or offline"
    if ($smoke) { $smoke | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray } }
} else {
    Write-Host "Updater smoke test passed (exit $code)" -ForegroundColor Green
}

Write-Sha256 $Target
