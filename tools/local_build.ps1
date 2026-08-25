param(
    [switch]$RebuildUpdater,
    [string]$QUpdateToolPath = $env:QUPDATETOOL_DIR
)

<# 
This script is designed to test our build workflow locally.

It performs the following steps:
1. Installs Python dependencies from requirements.txt
2. Loads version info from config.yaml
3. Builds the branded updater (calls build_updater.ps1); the installer
   requires it, so a missing updater aborts the Inno Setup compile
4. Builds Windows binaries using PyInstaller (calls build.ps1)
5. Builds Windows installer using Inno Setup (calls ISCC.exe)
6. Optionally signs artifacts with GPG if available
#>

$ErrorActionPreference = "Stop"

# Ensure script runs from repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "QSnippet Local Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

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

# Forwarded to tools\build_updater.ps1; -RebuildUpdater forces a fresh
# updater build instead of reusing whatever sits in output\windows.
$updaterArgs = @{}
if ($RebuildUpdater) { $updaterArgs["Force"] = $true }
if ($QUpdateToolPath) { $updaterArgs["QUpdateToolPath"] = $QUpdateToolPath }

# Step 1: Install dependencies
Write-Host "`n[1/5] Installing Python dependencies..." -ForegroundColor Cyan
<# pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install dependencies"
} #>

# Step 2: Load version info
Write-Host "`n[2/5] Loading version info..." -ForegroundColor Cyan
$VERSION = python -c "import yaml; print(yaml.safe_load(open('config/config.yaml'))['version'])"
Write-Host "Version: $VERSION" -ForegroundColor Green

$distDir = "output\windows"

# Step 3: Build the branded updater
# QSnippet.iss requires output\windows\updater.exe, and CI supplies it from
# the build_updater workflow. Locally we have to build it ourselves or the
# Inno Setup compile aborts on a missing source file.
Write-Host "`n[3/5] Building branded updater..." -ForegroundColor Cyan
& .\tools\build_updater.ps1 @updaterArgs
if (-not (Test-Path "$distDir\updater.exe")) {
    Write-Error "Updater build did not produce $distDir\updater.exe"
}

# Stamp the same hash CI stamps, so a locally installed build verifies the
# updater before launching it exactly as a released build does.
$env:UPDATER_SHA256 = Get-Sha256 "$distDir\updater.exe"
Write-Host "Updater SHA-256: $($env:UPDATER_SHA256)" -ForegroundColor Green

# Step 4: Build Windows binaries (PyInstaller)
Write-Host "`n[4/5] Building Windows binaries with PyInstaller..." -ForegroundColor Cyan
& .\tools\build.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed"
}

Write-Host "Waiting for operating system to release lock..." -ForegroundColor DarkGray
Start-Sleep -Seconds 2

# Step 5: Build Windows installer (Inno Setup)
Write-Host "`n[5/5] Building Inno Setup installer..." -ForegroundColor Cyan

# Find Inno Setup compiler
$innoSetupPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    "C:\Program Files\Inno Setup 5\ISCC.exe"
)

$isccPath = $null
foreach ($path in $innoSetupPaths) {
    if (Test-Path $path) {
        $isccPath = $path
        break
    }
}

if (-not $isccPath) {
    Write-Error "Inno Setup compiler (ISCC.exe) not found. Please install Inno Setup."
}

Write-Host "Found ISCC: $isccPath" -ForegroundColor Green

Write-Host "Waiting for operating system to release lock..." -ForegroundColor DarkGray
Start-Sleep -Seconds 2

# Update version in Inno Setup script
Write-Host "Updating Inno Setup version to $VERSION..." -ForegroundColor Cyan
$issFile = "QSnippet.iss"
$issContent = Get-Content $issFile -Raw
$originalContent = $issContent
$issContent = $issContent -replace '#define MyAppVersion ".*"', "#define MyAppVersion ""$VERSION"""
Set-Content $issFile $issContent -NoNewline

$maxRetries = 3
$retryCount = 0
$buildSuccess = $false

while ($retryCount -lt $maxRetries -and -not $buildSuccess) {
    if ($retryCount -gt 0) {
        Write-Host "Retrying Inno Setup build (attempt $($retryCount + 1)/$maxRetries)..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }

    & $isccPath /O+ "QSnippet.iss"

    if ($LASTEXITCODE -eq 0) {
        $buildSuccess = $true
    } else {
        $retryCount++
    }
}

# Restore original Inno Setup script
Set-Content $issFile $originalContent -NoNewline

if (-not $buildSuccess) {
    Write-Error @"
Inno Setup build failed after $maxRetries attempts.

This is usually caused by:
1. Antivirus software locking files in the output folder
   → Exclude 'output' folder from your antivirus scanning
2. Windows Explorer or another process using the files
   → Close the Explorer window and try again
3. Previous build process still running
   → Wait a moment and try again

Common antivirus exclusion paths:
- Windows Defender: Settings > Virus & threat protection > Manage settings > Exclusions
- Other antivirus: See your antivirus documentation
"@
}

Write-Host "Waiting for operating system to release lock..." -ForegroundColor DarkGray
Start-Sleep -Seconds 2

# Step 5: Optional GPG signing
Write-Host "`n[5/5] Signing artifacts (optional)..." -ForegroundColor Cyan

# Check if GPG is available
$gpgPath = Get-Command gpg -ErrorAction SilentlyContinue
if ($gpgPath) {
    Write-Host "GPG is available. Sign artifacts? (y/n)" -ForegroundColor Yellow
    $response = Read-Host

    if ($response -eq "y" -or $response -eq "Y") {
        # Generate SHA256 checksums
        Write-Host "Generating SHA256SUMS..." -ForegroundColor Cyan
        $sha256Output = @()
        Get-ChildItem "$distDir\*.exe" | ForEach-Object {
            $hash = Get-Sha256 $_.FullName
            $sha256Output += "$hash  $($_.Name)"
        }
        $sha256Output | Out-File "$distDir\SHA256SUMS.txt" -Encoding ASCII
        Write-Host "SHA256SUMS.txt created" -ForegroundColor Green

        # Sign SHA256SUMS file
        Write-Host "Signing SHA256SUMS.txt..." -ForegroundColor Cyan
        & gpg --batch --yes --detach-sign "$distDir\SHA256SUMS.txt"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "SHA256SUMS.txt signed (SHA256SUMS.txt.sig)" -ForegroundColor Green
        } else {
            Write-Warning "Failed to sign SHA256SUMS.txt"
        }

        # Sign each .exe file
        Write-Host "Signing .exe files..." -ForegroundColor Cyan
        Get-ChildItem "$distDir\*.exe" | ForEach-Object {
            & gpg --batch --yes --detach-sign $_.FullName
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Signed: $($_.Name)" -ForegroundColor Green
            } else {
                Write-Warning "Failed to sign: $($_.Name)"
            }
        }
    } else {
        Write-Host "Skipping GPG signing" -ForegroundColor Yellow
    }
} else {
    Write-Host "GPG not found. Skipping signature verification." -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Installer: output\windows\QSnippet-$VERSION-windows-installer.exe" -ForegroundColor Cyan
Write-Host "Portable:  output\windows\QSnippet-$VERSION-windows-portable.exe" -ForegroundColor Cyan

$openFolder = Read-Host "Open output folder in File Explorer? (y/n)"
if ($openFolder -match '^[Yy]') {
    explorer.exe (Resolve-Path $distDir)
}
