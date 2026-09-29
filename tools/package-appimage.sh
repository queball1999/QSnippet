#!/bin/bash
set -euo pipefail

# Packages the PyInstaller binary from tools/build.sh into an AppImage.
#
# The AppDir mirrors the .deb install layout (binary, updater, config/,
# assets/, notices/ side by side), so the app resolves everything relative to
# its executable exactly as it does from /opt/QSnippet. The AppImage mount is
# read-only, same as /opt, so nothing new is asked of the app at runtime.

# Always run from repo root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

APP_NAME="QSnippet"
OUTPUT_DIR="output/linux"
APPDIR="build/$APP_NAME.AppDir"
APP_ROOT="$APPDIR/usr/lib/qsnippet"
TOOLS_DIR="build/tools"

# Pinned rather than "continuous", so an upstream change can't silently alter
# what ships. Bump deliberately.
APPIMAGETOOL_VERSION="1.9.1"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|aarch64) ;;
  *) echo "ERROR: unsupported architecture for AppImage: $ARCH" >&2; exit 1 ;;
esac

VERSION=$(python3 -c "import yaml; print(yaml.safe_load(open('config/config.yaml'))['version'])")
LINUX_BUILD="$OUTPUT_DIR/$APP_NAME-$VERSION"
APPIMAGE_PATH="$OUTPUT_DIR/$APP_NAME-$VERSION-$ARCH.AppImage"

echo "Packaging $APP_NAME v$VERSION as an AppImage ($ARCH)"

if [ ! -f "$LINUX_BUILD" ]; then
  echo "ERROR: Linux binary not found at $LINUX_BUILD" >&2
  echo "Run tools/build.sh first" >&2
  exit 1
fi

for f in deb-package/qsnippet.desktop assets/icons/icon_128x128.png; do
  if [ ! -f "$f" ]; then
    echo "ERROR: $f not found; appimagetool cannot build without it" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# AppDir
# ---------------------------------------------------------------------------
rm -rf "$APPDIR"
mkdir -p "$APP_ROOT/config" "$APP_ROOT/assets" "$APP_ROOT/notices"

cp "$LINUX_BUILD" "$APP_ROOT/$APP_NAME"
chmod 755 "$APP_ROOT/$APP_NAME"

# Mode 755, not 775: QSnippet hash-verifies this binary before launching it.
# Inside an AppImage the updater swaps the whole image in place ($APPIMAGE).
if [ -f "$OUTPUT_DIR/updater" ]; then
  cp "$OUTPUT_DIR/updater" "$APP_ROOT/updater"
  chmod 755 "$APP_ROOT/updater"
  echo "Packaged updater binary"
else
  echo "WARNING: no updater binary at $OUTPUT_DIR/updater; in-app updates will be unavailable" >&2
fi

cp -r assets/icons  "$APP_ROOT/assets/icons"
cp -r assets/images "$APP_ROOT/assets/images"
rm -rf "$APP_ROOT/assets/icons/old"
find "$APP_ROOT/assets" \( -name Thumbs.db -o -name .DS_Store \) -delete 2>/dev/null || true

for f in config.yaml settings.yaml updater.yaml; do
  cp "config/$f" "$APP_ROOT/config/$f"
done

cp -a notices/. "$APP_ROOT/notices/"
cp LICENSE README.md "$APP_ROOT/"

# Desktop integration: appimagetool requires exactly one .desktop file and a
# matching icon at the AppDir root.
cp deb-package/qsnippet.desktop "$APPDIR/qsnippet.desktop"
cp assets/icons/icon_128x128.png "$APPDIR/qsnippet.png"
ln -sf qsnippet.png "$APPDIR/.DirIcon"

for size in 16 32 64 128; do
  src="assets/icons/icon_${size}x${size}.png"
  if [ -f "$src" ]; then
    dest="$APPDIR/usr/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$dest"
    cp "$src" "$dest/qsnippet.png"
  fi
done

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/qsnippet/QSnippet" "$@"
EOF
chmod 755 "$APPDIR/AppRun"

# ---------------------------------------------------------------------------
# appimagetool
# ---------------------------------------------------------------------------
APPIMAGETOOL="${APPIMAGETOOL:-}"
if [ -z "$APPIMAGETOOL" ]; then
  APPIMAGETOOL="$TOOLS_DIR/appimagetool-$APPIMAGETOOL_VERSION-$ARCH.AppImage"
  if [ ! -x "$APPIMAGETOOL" ]; then
    mkdir -p "$TOOLS_DIR"
    echo "Downloading appimagetool $APPIMAGETOOL_VERSION..."
    curl -fsSL -o "$APPIMAGETOOL" \
      "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VERSION/appimagetool-$ARCH.AppImage"
    chmod 755 "$APPIMAGETOOL"
  fi
fi

mkdir -p "$OUTPUT_DIR"
rm -f "$APPIMAGE_PATH"

# Extract-and-run: CI runners (and containers) usually have no FUSE.
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$APPIMAGETOOL" --no-appstream "$APPDIR" "$APPIMAGE_PATH"

if [ ! -f "$APPIMAGE_PATH" ]; then
  echo "ERROR: appimagetool reported success but $APPIMAGE_PATH does not exist" >&2
  exit 1
fi
chmod 755 "$APPIMAGE_PATH"

echo ""
echo "AppImage created:"
echo "  $APPIMAGE_PATH ($(du -h "$APPIMAGE_PATH" | cut -f1))"
