#!/bin/bash
set -euo pipefail

# Always run from repo root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

APP_NAME="QSnippet"
ARCH="amd64"
PKG_ROOT="package"
OUTPUT_DIR="output/linux"
INSTALL_DIR="$PKG_ROOT/opt/QSnippet"

WARN_COUNT=0
MISSING_REQUIRED=()

warn() {
  echo "WARNING: $*" >&2
  WARN_COUNT=$((WARN_COUNT + 1))
}

fail_required() {
  echo "ERROR: $*" >&2
  MISSING_REQUIRED+=("$1")
}

# Fail once with the complete list rather than on the first missing item,
# so a broken checkout is diagnosed in a single run.
abort_if_missing_required() {
  if [ ${#MISSING_REQUIRED[@]} -gt 0 ]; then
    echo "" >&2
    echo "Packaging aborted; ${#MISSING_REQUIRED[@]} required item(s) missing:" >&2
    printf '  - %s\n' "${MISSING_REQUIRED[@]}" >&2
    exit 1
  fi
}

# Required build tools
for tool in python3 dpkg-deb; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    fail_required "required tool '$tool' is not installed"
  fi
done
abort_if_missing_required

# Required inputs that everything else depends on
if [ ! -f "config/config.yaml" ]; then
  fail_required "config/config.yaml not found (needed for version and asset names)"
fi
abort_if_missing_required

# Read version from config
VERSION=$(python3 - <<'PYEOF'
import sys

import yaml

try:
    cfg = yaml.safe_load(open("config/config.yaml"))
except Exception as exc:
    sys.exit(f"could not parse config/config.yaml: {exc}")

version = (cfg or {}).get("version")
if not version:
    sys.exit("no 'version' key in config/config.yaml")
print(version)
PYEOF
)

if [ -z "$VERSION" ]; then
  fail_required "could not read version from config/config.yaml"
  abort_if_missing_required
fi

# dpkg requires a version starting with a digit
if ! [[ "$VERSION" =~ ^[0-9] ]]; then
  fail_required "version '$VERSION' is not a valid Debian version (must start with a digit)"
  abort_if_missing_required
fi

if [[ "$VERSION" == *dev* ]]; then
  warn "version '$VERSION' looks like a development build; do not publish this package"
fi

LINUX_BUILD="$OUTPUT_DIR/${APP_NAME}-${VERSION}"

echo "Packaging $APP_NAME v$VERSION for Debian"

# Check for built binary
if [ ! -f "$LINUX_BUILD" ]; then
  echo "ERROR: Linux binary not found at $LINUX_BUILD" >&2
  echo "Run tools/build.sh first" >&2
  exit 1
fi

# Everything under deb-package/ ships inside the package itself
for f in control postinst postrm qsnippet.desktop qsnippet.metainfo.xml; do
  if [ ! -f "deb-package/$f" ]; then
    if [ "$f" = "control" ]; then
      fail_required "deb-package/control not found (dpkg-deb cannot build without it)"
    else
      warn "deb-package/$f not found; that part of the package will be skipped"
    fi
  fi
done
abort_if_missing_required

# Clean old packaging artifacts
rm -rf "$PKG_ROOT"

# Create directory structure.
# assets/ mirrors the layout the app resolves at runtime: it looks for
# <executable dir>/assets/images and <executable dir>/assets/icons.
mkdir -p \
  "$PKG_ROOT/DEBIAN" \
  "$INSTALL_DIR" \
  "$INSTALL_DIR/assets/images" \
  "$INSTALL_DIR/assets/icons" \
  "$INSTALL_DIR/config" \
  "$INSTALL_DIR/notices" \
  "$PKG_ROOT/usr/bin" \
  "$PKG_ROOT/usr/share/applications" \
  "$PKG_ROOT/usr/share/metainfo"

# Copy application binary
cp "$LINUX_BUILD" "$INSTALL_DIR/QSnippet"
chmod 755 "$INSTALL_DIR/QSnippet"

# Copy a directory tree, tolerating an empty or absent source.
# Uses src/. so dotfiles are included and an empty directory is not an error.
copy_tree() {
  local src="$1"
  local dest="$2"
  local label="$3"

  if [ ! -d "$src" ]; then
    warn "$label not found at $src; skipping"
    return 0
  fi

  if [ -z "$(ls -A "$src" 2>/dev/null)" ]; then
    warn "$label at $src is empty; skipping"
    return 0
  fi

  cp -a "$src/." "$dest/"
}

# assets/images - runtime images referenced by config.yaml
copy_tree "assets/images" "$INSTALL_DIR/assets/images" "Application images"

# assets/icons - tray icon and every UI SVG
copy_tree "assets/icons" "$INSTALL_DIR/assets/icons" "Application icons"

# Drop artifacts that should never ship
rm -rf "$INSTALL_DIR/assets/icons/old"
find "$INSTALL_DIR/assets" \
  \( -name "Thumbs.db" -o -name ".DS_Store" -o -name "__pycache__" \) \
  -exec rm -rf {} + 2>/dev/null || true

# Warn when an asset declared in config.yaml did not make it into the package
MISSING_ASSETS=$(ASSET_ROOT="$INSTALL_DIR/assets" python3 - <<'PYEOF'
import os
from pathlib import Path

import yaml

root = Path(os.environ["ASSET_ROOT"])
cfg = yaml.safe_load(open("config/config.yaml")) or {}
missing = []

for key, name in (cfg.get("images") or {}).items():
    if not name or name == "QSnippet":
        # Generic placeholder, resolved per-OS at runtime
        continue
    if not any((root / sub / name).is_file() for sub in ("images", "icons")):
        missing.append(f"{key} ({name})")

print("\n".join(missing))
PYEOF
)

if [ -n "$MISSING_ASSETS" ]; then
  while IFS= read -r asset; do
    [ -n "$asset" ] && warn "asset declared in config.yaml is not in the package: $asset"
  done <<< "$MISSING_ASSETS"
fi

# Desktop icons - install each available size into its matching hicolor dir
ICON_INSTALLED=0
for size in 16 32 64 128; do
  src="assets/icons/icon_${size}x${size}.png"
  if [ -f "$src" ]; then
    dest="$PKG_ROOT/usr/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$dest"
    cp "$src" "$dest/qsnippet.png"
    ICON_INSTALLED=$((ICON_INSTALLED + 1))
  fi
done
if [ "$ICON_INSTALLED" -eq 0 ]; then
  warn "no assets/icons/icon_NxN.png found; the package will have no desktop icon"
fi

# config/ - config.yaml holds the version and asset names, settings.yaml seeds defaults
for f in config.yaml settings.yaml; do
  if [ -f "config/$f" ]; then
    cp "config/$f" "$INSTALL_DIR/config/$f"
  else
    warn "config/$f not found; skipping"
  fi
done

# notices/ - release notices shown in-app
copy_tree "notices" "$INSTALL_DIR/notices" "Release notices"

# LICENSE / README
for f in LICENSE README.md; do
  if [ -f "$f" ]; then
    cp "$f" "$INSTALL_DIR/$f"
  else
    warn "$f not found; skipping"
  fi
done

# Launcher script
cat > "$PKG_ROOT/usr/bin/qsnippet" <<'EOF'
#!/bin/sh
exec /opt/QSnippet/QSnippet "$@"
EOF
chmod 755 "$PKG_ROOT/usr/bin/qsnippet"

# Desktop entry
if [ -f "deb-package/qsnippet.desktop" ]; then
  cp deb-package/qsnippet.desktop \
     "$PKG_ROOT/usr/share/applications/qsnippet.desktop"
else
  warn "no desktop entry; QSnippet will not appear in the application menu"
fi

# AppData metadata (for software centers)
if [ -f "deb-package/qsnippet.metainfo.xml" ]; then
  cp deb-package/qsnippet.metainfo.xml \
     "$PKG_ROOT/usr/share/metainfo/qsnippet.metainfo.xml"
else
  warn "no metainfo.xml; the package will not show up in software centers"
fi

# Control file
sed "s/VERSION_REPLACED_DURING_BUILD/$VERSION/g" \
  deb-package/control \
  > "$PKG_ROOT/DEBIAN/control"

if grep -q "VERSION_REPLACED_DURING_BUILD" "$PKG_ROOT/DEBIAN/control"; then
  echo "ERROR: version placeholder was not substituted in DEBIAN/control" >&2
  exit 1
fi

# Maintainer scripts
for f in postinst postrm; do
  if [ -f "deb-package/$f" ]; then
    cp "deb-package/$f" "$PKG_ROOT/DEBIAN/$f"
    chmod 755 "$PKG_ROOT/DEBIAN/$f"
  else
    warn "deb-package/$f not found; skipping maintainer script"
  fi
done

# Build .deb
mkdir -p "$OUTPUT_DIR"
DEB_PATH="$OUTPUT_DIR/${APP_NAME}_${VERSION}_${ARCH}.deb"
dpkg-deb --build "$PKG_ROOT" "$DEB_PATH"

if [ ! -f "$DEB_PATH" ]; then
  echo "ERROR: dpkg-deb reported success but $DEB_PATH does not exist" >&2
  exit 1
fi

echo ""
echo "Debian package created:"
echo "  $DEB_PATH ($(du -h "$DEB_PATH" | cut -f1))"

if [ "$WARN_COUNT" -gt 0 ]; then
  echo ""
  echo "Completed with $WARN_COUNT warning(s); see the log above."
fi
