#!/usr/bin/env bash
#
# Build the QSnippet-branded updater locally, the way CI does.
#
# CI builds the updater in .github/workflows/build_updater.yaml and hands it
# to the packaging job as an artifact. A local build had no equivalent, so
# package-deb.sh warned and shipped a .deb with no updater in it (and on
# Windows the Inno Setup compile aborted outright).
#
# The result is NOT the binary that ships. CI pins QUpdateTool to a tag; a
# local checkout is whatever you have. Use this for local install testing.
#
#   ./tools/build_updater.sh              # build if missing
#   FORCE=1 ./tools/build_updater.sh      # always rebuild
#   QUPDATETOOL_DIR=/path/to/QUpdateTool ./tools/build_updater.sh
#
# Writes output/linux/updater and prints its SHA-256, which the caller passes
# to build.sh as UPDATER_SHA256 so build_info.py carries the same stamp a CI
# build would.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

DIST_DIR="$REPO_ROOT/output/linux"
TARGET="$DIST_DIR/updater"
GUI="${GUI:-1}"

print_hash() {
  local digest
  digest=$(sha256sum "$TARGET" | cut -d' ' -f1)
  echo "Updater SHA-256: $digest"
}

if [ -f "$TARGET" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "Updater already present: $TARGET (set FORCE=1 to rebuild)"
  print_hash
  exit 0
fi

# Locate a QUpdateTool checkout: QUPDATETOOL_DIR, then the usual siblings.
if [ -z "${QUPDATETOOL_DIR:-}" ]; then
  for name in QUpdateTool2.0 QUpdateTool; do
    candidate="$(dirname "$REPO_ROOT")/$name"
    if [ -f "$candidate/tools/build_branded.py" ]; then
      QUPDATETOOL_DIR="$candidate"
      break
    fi
  done
fi

if [ -z "${QUPDATETOOL_DIR:-}" ] || [ ! -f "$QUPDATETOOL_DIR/tools/build_branded.py" ]; then
  cat >&2 <<'MSG'
error: no QUpdateTool checkout found.

Clone it next to this repo, or point at it explicitly:
    git clone https://github.com/queball1999/QUpdateTool.git ../QUpdateTool
    QUPDATETOOL_DIR=<path> ./tools/build_updater.sh
MSG
  exit 1
fi

QUPDATETOOL_DIR="$(cd "$QUPDATETOOL_DIR" && pwd)"
echo "Building branded updater from $QUPDATETOOL_DIR"

if [ "$GUI" = "1" ]; then
  python3 -m pip install -q -r "$QUPDATETOOL_DIR/requirements-gui.txt"
else
  python3 -m pip install -q -r "$QUPDATETOOL_DIR/requirements.txt"
fi

mkdir -p "$DIST_DIR"

gui_flag=""
[ "$GUI" = "1" ] && gui_flag="--gui"

(
  cd "$QUPDATETOOL_DIR"
  # shellcheck disable=SC2086
  python3 tools/build_branded.py \
    --brand "$REPO_ROOT/config/updater.yaml" \
    --icon  "$REPO_ROOT/assets/icons/QSnippet.icns" \
    --key   "$REPO_ROOT/gpg-public.asc" \
    --name  updater \
    --out   "$TARGET" \
    $gui_flag \
    --clean
)

[ -f "$TARGET" ] || { echo "error: build reported success but $TARGET is missing" >&2; exit 1; }
chmod +x "$TARGET"

# Same smoke test CI runs: exit 10 (update available) or 11 (up to date)
# proves the brand, pinned key, and release backend all resolved.
set +e
"$TARGET" --check-only --current-version 0.0.0 --log-file none >/dev/null 2>&1
code=$?
set -e
if [ "$code" != "10" ] && [ "$code" != "11" ]; then
  echo "warning: updater --check-only exited with $code; it may be misconfigured or offline" >&2
else
  echo "Updater smoke test passed (exit $code)"
fi

print_hash
