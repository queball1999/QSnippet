# -*- mode: python ; coding: utf-8 -*-
"""
One build spec for every OS.

tools/build.ps1 (Windows) and tools/build.sh (Linux/macOS) both run
`pyinstaller QSnippet.spec`, so this file is the single place that decides
what lands in the bundle. Per-OS differences (icon format, binary name) are
branched on sys.platform below.

The onefile bundle carries assets/icons and assets/images internally as a
fallback; the portable and installed layouts also drop a loose assets/ folder
next to the executable, which the app prefers when present
(see utils/file_utils.py: resolve_images_path / resolve_asset_with_fallback).
"""
import sys
from pathlib import Path

import yaml
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)  # noqa: F821  (injected by PyInstaller)

# Version drives the binary name on Linux/macOS, where build.sh and
# tools/package-deb.sh expect output/<os>/QSnippet-<version>.
_cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8")) or {}
VERSION = str(_cfg.get("version") or "0.0.0")

IS_WIN = sys.platform == "win32"

APP_NAME = "QSnippet" if IS_WIN else f"QSnippet-{VERSION}"
ICON = str(ROOT / "assets" / "icons" / ("QSnippet.ico" if IS_WIN else "QSnippet.icns"))

# Runtime asset tree. Ship icons and images; skip assets/videos (demo media,
# not used at runtime) and assets/icons/old (superseded art).
datas = [
    (str(ROOT / "assets" / "icons"), "assets/icons"),
    (str(ROOT / "assets" / "images"), "assets/images"),
]
binaries = []
hiddenimports = []

# pynput ships per-platform backends that PyInstaller's static analysis misses.
_pyn_datas, _pyn_binaries, _pyn_hidden = collect_all("pynput")
datas += _pyn_datas
binaries += _pyn_binaries
hiddenimports += _pyn_hidden

a = Analysis(
    ['QSnippet.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON],
)
