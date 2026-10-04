#!/bin/bash

set -euo pipefail

# Ensure script runs from repo root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# Extract version from config.yaml
VERSION=$(python3 -c "import yaml; print(yaml.safe_load(open('config/config.yaml'))['version'])")

APP_NAME="QSnippet"
DIST_DIR="output"
BUILD_DIR="build"

echo "Building $APP_NAME v$VERSION..."

# Detect OS -> output subdirectory
OS=$(uname -s)
case "$OS" in
  Linux*)  OS_DIR="linux" ;;
  Darwin*) OS_DIR="macos" ;;
  *) echo "Unsupported OS: $OS" >&2; exit 1 ;;
esac
echo "Detected OS: $OS (output/$OS_DIR)"

OUT="$DIST_DIR/$OS_DIR"
BIN="$OUT/$APP_NAME-$VERSION"

# Clean only our own artifacts. Do NOT wipe "$DIST_DIR" wholesale: CI (and
# `make build`) place the branded updater at "$OUT/updater" before this runs,
# and package-deb.sh needs it. QSnippet.spec is committed source, not an
# artifact, so it is never removed here.
rm -rf "$BUILD_DIR" "$BIN" "$OUT/$APP_NAME-$VERSION-portable"

# Generate build metadata. MUST happen before PyInstaller runs.
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Set by CI (and tools/build_updater.sh) after the updater is built; QSnippet
# verifies the updater against this hash before launching it.
UPDATER_SHA256="${UPDATER_SHA256:-}"

cat > config/build_info.py <<EOF
BUILD_VERSION = "$VERSION"
BUILD_DATE = "$BUILD_DATE"
BUILD_COMMIT = "$GIT_COMMIT"
UPDATER_SHA256 = "$UPDATER_SHA256"
EOF
echo "Generated build_info.py ($BUILD_DATE, commit $GIT_COMMIT)"

# Build the onefile binary. What goes into the bundle (icon, name, bundled
# assets) lives in QSnippet.spec so Linux/macOS and Windows stay in lockstep;
# only output locations are passed here.
pyinstaller --noconfirm --clean \
  --distpath "$OUT" \
  --workpath "$BUILD_DIR/work" \
  QSnippet.spec

[ -f "$BIN" ] || { echo "ERROR: expected binary not found: $BIN" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Portable archive
# ---------------------------------------------------------------------------
echo "Creating portable zip package..."
PORTABLE_DIR="$OUT/$APP_NAME-$VERSION-portable"
PORTABLE_ZIP="$DIST_DIR/$APP_NAME-$VERSION-$OS_DIR-portable.zip"

rm -f "$PORTABLE_ZIP"
mkdir -p "$PORTABLE_DIR" "$DIST_DIR"
PORTABLE_ZIP_ABS="$(cd "$DIST_DIR" && pwd)/$(basename "$PORTABLE_ZIP")"

# Executable
cp "$BIN" "$PORTABLE_DIR/$APP_NAME"
chmod 755 "$PORTABLE_DIR/$APP_NAME"

# Loose asset tree the app prefers over its bundled copy (icons + images only)
mkdir -p "$PORTABLE_DIR/assets"
cp -r assets/icons  "$PORTABLE_DIR/assets/icons"
cp -r assets/images "$PORTABLE_DIR/assets/images"
rm -rf "$PORTABLE_DIR/assets/icons/old"
find "$PORTABLE_DIR/assets" \( -name Thumbs.db -o -name .DS_Store \) -delete 2>/dev/null || true

# config/ (config.yaml, settings.yaml, updater.yaml); drop build artifacts
cp -r config "$PORTABLE_DIR/config"
rm -rf "$PORTABLE_DIR/config/__pycache__"
rm -f "$PORTABLE_DIR/config/build_info.py"

# Release notices shown in-app
cp -r notices "$PORTABLE_DIR/notices"

# Branded updater so in-app updates work from the portable build too
if [ -f "$OUT/updater" ]; then
  cp "$OUT/updater" "$PORTABLE_DIR/updater"
  chmod 755 "$PORTABLE_DIR/updater"
else
  echo "warning: $OUT/updater not found; portable build will have no in-app updater" >&2
fi

cp LICENSE "$PORTABLE_DIR/LICENSE"

( cd "$OUT" && zip -r "$PORTABLE_ZIP_ABS" "$(basename "$PORTABLE_DIR")" )

echo "Created portable zip: $PORTABLE_ZIP"
echo "Build complete: $OUT"
