#!/bin/bash

set -e

APP_NAME="QSnippet"
ENTRY="QSnippet.py"
DIST_DIR="output"
BUILD_DIR="build"
ICON_LINUX="./images/QSnippet.png"
ICON_WINDOWS="./images/QSnippet.ico"
ICON_MAC="./images/QSnippet.icns"

OS=$(uname -s)
PYINSTALLER_ARGS="--noconfirm --onefile --windowed"

echo "Building $APP_NAME on $OS..."

# Clean previous build artifacts
rm -rf "$DIST_DIR" "$BUILD_DIR" "$APP_NAME.spec"

# Detect and build per OS
case "$OS" in
  Linux*)
    echo "Target: Linux"
    pyinstaller $PYINSTALLER_ARGS --icon="$ICON_LINUX" --distpath "$DIST_DIR/linux" "$ENTRY"
    ;;

  Darwin*)
    echo "Target: macOS"
    pyinstaller $PYINSTALLER_ARGS --icon="$ICON_MAC" --distpath "$DIST_DIR/macos" "$ENTRY"
    ;;

  MINGW*|MSYS*|CYGWIN*|Windows_NT)
    echo "Target: Windows"
    pyinstaller $PYINSTALLER_ARGS --icon="$ICON_WINDOWS" --distpath "$DIST_DIR/windows" "$ENTRY"
    ;;

  *)
    echo "Unsupported OS: $OS"
    exit 1
    ;;
esac

echo "Build complete for $OS."
