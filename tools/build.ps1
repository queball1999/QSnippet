param()

$ErrorActionPreference = "Stop"

# Ensure script runs from repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

# Extract version from config.yaml using Python
# updating dir 12/22/25 to reflect new config path
$VERSION = python -c "import yaml; print(yaml.safe_load(open('config\config.yaml'))['version'])"

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

# Create portable version
# NOTE:
# exePath (QSnippet.exe) is intentionally left for Inno Setup.
# It is not uploaded as an artifact.
$exePath     = Join-Path $DIST_DIR "$APP_NAME.exe"
$portableExe = Join-Path $DIST_DIR "$APP_NAME-$VERSION-windows-portable.exe"

if (Test-Path $exePath) {
    Copy-Item $exePath $portableExe -Force
    Write-Host "Created portable binary: $portableExe" -ForegroundColor Cyan
} else {
    Write-Error "Expected binary not found: $exePath" -ForegroundColor Yellow
}

Write-Host "Build complete: $DIST_DIR" -ForegroundColor Green
