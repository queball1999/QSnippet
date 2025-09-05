# build.ps1
param()

$ErrorActionPreference = "Stop"

# Extract version from config.yaml using Python
$VERSION = python -c "import yaml; print(yaml.safe_load(open('config.yaml'))['version'])"

$APP_NAME   = "QSnippet"
$ENTRY      = "QSnippet.py"
$DIST_DIR   = "output"
$BUILD_DIR  = "build"
$ICON_LINUX = "./images/QSnippet.png"
$ICON_WINDOWS = "./images/QSnippet.ico"
$ICON_MAC   = "./images/QSnippet.icns"

$PYINSTALLER_ARGS = "--noconfirm --onefile --windowed"

Write-Host "Building $APP_NAME v$VERSION..."

# Clean old build artifacts
if (Test-Path $DIST_DIR) { Remove-Item $DIST_DIR -Recurse -Force }
if (Test-Path $BUILD_DIR) { Remove-Item $BUILD_DIR -Recurse -Force }
if (Test-Path "$APP_NAME.spec") { Remove-Item "$APP_NAME.spec" -Force }

# Detect OS
$OS = $env:OS
if (-not $OS) {
    # Fallback for non-Windows systems
    $OS = (uname -s)
}
Write-Host "Detected OS: $OS"

switch -Regex ($OS) {
    "Windows_NT" {
        Write-Host "Building for Windows..."
        & pyinstaller $PYINSTALLER_ARGS `
            --icon=$ICON_WINDOWS `
            --distpath "$DIST_DIR/windows" `
            --name "$APP_NAME-$VERSION" `
            $ENTRY
    }
    "Darwin" {
        Write-Host "Building for macOS..."
        & pyinstaller $PYINSTALLER_ARGS `
            --icon=$ICON_MAC `
            --distpath "$DIST_DIR/macos" `
            --name "$APP_NAME-$VERSION" `
            $ENTRY
    }
    "Linux" {
        Write-Host "Building for Linux..."
        & pyinstaller $PYINSTALLER_ARGS `
            --icon=$ICON_LINUX `
            --distpath "$DIST_DIR/linux" `
            --name "$APP_NAME-$VERSION" `
            $ENTRY
    }
    default {
        Write-Error "Unsupported OS: $OS"
        exit 1
    }
}

Write-Host "Build complete: $DIST_DIR"
