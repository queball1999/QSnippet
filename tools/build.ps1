param()

$ErrorActionPreference = "Stop"

# Ensure script runs from repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

# Extract version from config.yaml using Python
$VERSION = python -c "import yaml; print(yaml.safe_load(open('config.yaml'))['version'])"

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

Write-Host "Running PyInstaller..."
& pyinstaller @PYINSTALLER_ARGS

# Create portable version
$exePath     = Join-Path $DIST_DIR "$APP_NAME.exe"
$portableExe = Join-Path $DIST_DIR "$APP_NAME-$VERSION-portable.exe"

if (Test-Path $exePath) {
    Copy-Item $exePath $portableExe -Force
    Write-Host "Created portable binary: $portableExe"
} else {
    Write-Error "Expected binary not found: $exePath"
}

Write-Host "Build complete: $DIST_DIR" -ForegroundColor Green
