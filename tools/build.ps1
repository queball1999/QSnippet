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

# Define custom paths to keep root clean
$BUILD_DIR    = "build"   # work + spec files
$DIST_DIR     = (Resolve-Path "./output/windows").Path

$PYINSTALLER_ARGS = @(
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--icon=$ICON_WINDOWS",
    "--distpath", $DIST_DIR,
    "--workpath", "$BUILD_DIR/work",
    "--specpath", "$BUILD_DIR/spec",
    "--name", "$APP_NAME-$VERSION",
    $ENTRY
)

Write-Host "Building $APP_NAME v$VERSION..."

# Clean old build artifacts
if (Test-Path $BUILD_DIR) { Remove-Item $BUILD_DIR -Recurse -Force }

# Detect OS
$OS = $env:OS
if (-not $OS) { $OS = (uname -s) }
Write-Host "Detected OS: $OS"

switch -Regex ($OS) {
    "Windows_NT" {
        Write-Host "Building for Windows..."
        Write-Host "Running: pyinstaller $PYINSTALLER_ARGS"
        & pyinstaller @PYINSTALLER_ARGS
    }
    default {
        Write-Error "Unsupported OS: $OS"
        exit 1
    }
}

Write-Host "Build complete: exe in repo root"
