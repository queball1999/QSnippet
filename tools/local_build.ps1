param()

<# 
This script is designed to test our build workflow locally.

It performs the following steps:
1. Installs Python dependencies from requirements.txt
2. Loads version info from config.yaml
3. Builds Windows binaries using PyInstaller (calls build.ps1)
4. Builds Windows installer using Inno Setup (calls ISCC.exe)
5. Optionally signs artifacts with GPG if available
#>

$ErrorActionPreference = "Stop"

# Ensure script runs from repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "QSnippet Local Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Step 1: Install dependencies
Write-Host "`n[1/4] Installing Python dependencies..." -ForegroundColor Cyan
<# pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install dependencies"
} #>

# Step 2: Load version info
Write-Host "`n[2/4] Loading version info..." -ForegroundColor Cyan
$VERSION = python -c "import yaml; print(yaml.safe_load(open('config\config.yaml'))['version'])"
Write-Host "Version: $VERSION" -ForegroundColor Green

# Step 3: Build Windows binaries (PyInstaller)
Write-Host "`n[3/4] Building Windows binaries with PyInstaller..." -ForegroundColor Cyan
& .\tools\build.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed"
}

Write-Host "Waiting for operating system to release lock..." -ForegroundColor DarkGray
Start-Sleep -Seconds 2

# Step 4: Build Windows installer (Inno Setup)
Write-Host "`n[4/4] Building Inno Setup installer..." -ForegroundColor Cyan

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

# Call Inno Setup with /F flag to set output filename with version
$installerFilename = "QSnippet-$VERSION-windows-installer"

$maxRetries = 3
$retryCount = 0
$buildSuccess = $false

while ($retryCount -lt $maxRetries -and -not $buildSuccess) {
    if ($retryCount -gt 0) {
        Write-Host "Retrying Inno Setup build (attempt $($retryCount + 1)/$maxRetries)..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }

    & $isccPath /F"$installerFilename" /O+ "QSnippet.iss"

    if ($LASTEXITCODE -eq 0) {
        $buildSuccess = $true
    } else {
        $retryCount++
    }
}

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
        $distDir = "output\windows"

        # Generate SHA256 checksums
        Write-Host "Generating SHA256SUMS..." -ForegroundColor Cyan
        $sha256Output = @()
        Get-ChildItem "$distDir\*.exe" | ForEach-Object {
            $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
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
