#!/bin/bash
set -e

# Always run from repo root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

APP_NAME="QSnippet"

# Read version from config
VERSION=$(python3 - <<EOF
import yaml
print(yaml.safe_load(open("config/config.yaml"))["version"])
EOF
)

ARCH="amd64"
PKG_ROOT="package"
OUTPUT_DIR="output/linux"
LINUX_BUILD="output/linux/${APP_NAME}-${VERSION}"

echo "Packaging $APP_NAME v$VERSION for Debian"

# Sanity checks
if [ ! -f "$LINUX_BUILD" ]; then
  echo "ERROR: Linux binary not found at $LINUX_BUILD"
  echo "Run tools/build.sh first"
  exit 1
fi

# Clean old packaging artifacts
rm -rf "$PKG_ROOT"
mkdir -p "$PKG_ROOT"

# Create directory structure
mkdir -p \
  "$PKG_ROOT/DEBIAN" \
  "$PKG_ROOT/opt/QSnippet" \
  "$PKG_ROOT/opt/QSnippet/config" \
  "$PKG_ROOT/opt/QSnippet/notices" \
  "$PKG_ROOT/usr/bin" \
  "$PKG_ROOT/usr/share/applications" \
  "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps"

# Copy application binary
cp "$LINUX_BUILD" "$PKG_ROOT/opt/QSnippet/QSnippet"
chmod 755 "$PKG_ROOT/opt/QSnippet/QSnippet"

# Copy Files
cp config/config.yaml   "$PKG_ROOT/opt/QSnippet/config/config.yaml"
cp config/settings.yaml "$PKG_ROOT/opt/QSnippet/config/settings.yaml"
cp -r notices/* "$PKG_ROOT/opt/QSnippet/notices/"
cp LICENSE   "$PKG_ROOT/opt/QSnippet/LICENSE"
cp README.md "$PKG_ROOT/opt/QSnippet/README.md"

# Launcher script
cat > "$PKG_ROOT/usr/bin/qsnippet" <<'EOF'
#!/bin/sh
exec /opt/QSnippet/QSnippet "$@"
EOF
chmod 755 "$PKG_ROOT/usr/bin/qsnippet"

# Desktop entry
cp deb-package/qsnippet.desktop \
   "$PKG_ROOT/usr/share/applications/qsnippet.desktop"

# Icon
cp images/icon_128x128.png \
   "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps/qsnippet.png"

# Control file
sed "s/VERSION_REPLACED_DURING_BUILD/$VERSION/g" \
  deb-package/control \
  > "$PKG_ROOT/DEBIAN/control"

# Maintainer scripts
cp deb-package/postinst "$PKG_ROOT/DEBIAN/postinst"
cp deb-package/postrm   "$PKG_ROOT/DEBIAN/postrm"
chmod 755 "$PKG_ROOT/DEBIAN/postinst" "$PKG_ROOT/DEBIAN/postrm"

# Build .deb
mkdir -p "$OUTPUT_DIR"
dpkg-deb --build "$PKG_ROOT" \
  "$OUTPUT_DIR/${APP_NAME}_${VERSION}_${ARCH}.deb"

echo "Debian package created:"
echo "  $OUTPUT_DIR/${APP_NAME}_${VERSION}_${ARCH}.deb"
