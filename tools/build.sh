#!/bin/bash

set -e

# Extract version from config.yaml using Python
VERSION=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['version'])")

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

  MINGW*|MSYS*|CYGWIN*|Windows_NT)
    echo "Building for Windows..."
    pyinstaller $PYINSTALLER_ARGS \
      --icon="$ICON_WINDOWS" \
      --distpath "$DIST_DIR/windows" \
      --name "$APP_NAME-$VERSION" \
      "$ENTRY"
    ;;

  *)
    echo "Unsupported OS: $OS"
    exit 1
    ;;
esac

echo "Build complete: $DIST_DIR"
