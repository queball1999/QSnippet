#!/bin/bash

set -e

# Ensure script runs from repo root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# Extract version from config.yaml using Python
# updating dir 12/22/25 to reflect new config path
VERSION=$(python3 -c "import yaml; print(yaml.safe_load(open('config/config.yaml'))['version'])")

APP_NAME="QSnippet"
ENTRY="QSnippet.py"
DIST_DIR="output"
BUILD_DIR="build"
ICON_LINUX="./images/QSnippet.png"
ICON_WINDOWS="./images/QSnippet.ico"
ICON_MAC="./images/QSnippet.icns"

PYINSTALLER_ARGS="--noconfirm --onefile --windowed"

echo "Building $APP_NAME v$VERSION..."

# Clean old build artifacts
rm -rf "$DIST_DIR" "$BUILD_DIR" "$APP_NAME.spec"

# Detect OS
OS=$(uname -s)
echo "Detected OS: $OS"

# Generate build metadata
# This MUST be done before running PyInstaller
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

cat > config/build_info.py <<EOF
BUILD_VERSION = "$VERSION"
BUILD_DATE = "$BUILD_DATE"
BUILD_COMMIT = "$GIT_COMMIT"
EOF

echo "Generated build_info.py ($BUILD_DATE, commit $GIT_COMMIT)"

case "$OS" in
  Linux*)
    echo "Building for Linux..."
    pyinstaller $PYINSTALLER_ARGS \
      --icon="$ICON_LINUX" \
      --distpath "$DIST_DIR/linux" \
      --name "$APP_NAME-$VERSION" \
      "$ENTRY"
    ;;

  Darwin*)
    echo "Building for macOS..."
    pyinstaller $PYINSTALLER_ARGS \
      --icon="$ICON_MAC" \
      --distpath "$DIST_DIR/macos" \
      --name "$APP_NAME-$VERSION" \
      "$ENTRY"
    ;;

  *)
    echo "Unsupported OS: $OS"
    exit 1
    ;;
esac

echo "Build complete: $DIST_DIR"
