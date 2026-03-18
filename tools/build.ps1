param()

$ErrorActionPreference = "Stop"

# Ensure script runs from repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

# Extract version from config.yaml using Python
# updating dir 12/22/25 to reflect new config path
$VERSION = python -c "import yaml; print(yaml.safe_load(open('config/config.yaml'))['version'])"

$APP_NAME     = "QSnippet"
$ENTRY        = "QSnippet.py"
$ICON_WINDOWS = (Resolve-Path "./images/QSnippet.ico").Path
$ImageDir     = Resolve-Path "./images"

# Define custom paths
$BUILD_DIR = "build"
$DIST_DIR  = "output/windows"

$PYINSTALLER_ARGS = @(
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--icon=$ICON_WINDOWS",
    "--distpath", $DIST_DIR,
    "--workpath", "$BUILD_DIR/work",
    "--specpath", "$BUILD_DIR/spec",
    "--name", $APP_NAME,
    "--add-data", "$ImageDir;images",
    $ENTRY
)

Write-Host "Building $APP_NAME v$VERSION..." -ForegroundColor Cyan

# Clean old build artifacts
if (Test-Path $BUILD_DIR) {
    Remove-Item $BUILD_DIR -Recurse -Force
}

# Generate build metadata
# This MUST be done before running PyInstaller
$BUILD_DATE = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$GIT_COMMIT = git rev-parse --short HEAD 2>$null

@"
BUILD_VERSION = "$VERSION"
BUILD_DATE = "$BUILD_DATE"
BUILD_COMMIT = "$GIT_COMMIT"
"@ | Out-File config/build_info.py -Encoding utf8

Write-Host "Generated build_info.py ($BUILD_DATE, commit $GIT_COMMIT)" -ForegroundColor Cyan

Write-Host "Running PyInstaller..."
& pyinstaller @PYINSTALLER_ARGS

# Create portable zip package
Write-Host "Creating portable zip package..." -ForegroundColor Cyan

$exePath     = Join-Path $DIST_DIR "$APP_NAME.exe"
$portableDir = Join-Path $DIST_DIR "QSnippet-$VERSION-windows-portable"
$portableZip = Join-Path $DIST_DIR "$APP_NAME-$VERSION-windows-portable.zip"

# Create temporary directory for packaging
if (Test-Path $portableDir) {
    Remove-Item $portableDir -Recurse -Force
}
New-Item -ItemType Directory -Path $portableDir | Out-Null

# Copy executable directly to portable directory
if (Test-Path $exePath) {
    Copy-Item $exePath (Join-Path $portableDir "$APP_NAME.exe") -Force
} else {
    Write-Error "Expected binary not found: $exePath" -ForegroundColor Yellow
}

# Copy config folder (excluding __pycache__ and build_info.py which are build artifacts)
$configDest = Join-Path $portableDir "config"
Copy-Item "config" $configDest -Recurse -Force
Remove-Item (Join-Path $configDest "__pycache__") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $configDest "build_info.py") -Force -ErrorAction SilentlyContinue

# Copy notices folder
Copy-Item "notices" (Join-Path $portableDir "notices") -Recurse -Force

# Copy license
Copy-Item "LICENSE" (Join-Path $portableDir "LICENSE") -Force

# Create zip file
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($portableDir, $portableZip, [System.IO.Compression.CompressionLevel]::Optimal, $false)

Write-Host "Created portable zip: $portableZip" -ForegroundColor Cyan

# Clean up temporary directory
Remove-Item $portableDir -Recurse -Force

Write-Host "Build complete: $DIST_DIR" -ForegroundColor Green
