# -*- mode: python ; coding: utf-8 -*-
# =========================================================
# Sooqify Image Updater - PyInstaller build spec
# Built automatically on GitHub-hosted Windows runners by
# .github/workflows/build-windows-exe.yml on every push to main / tag push.
#
# To build locally instead (from the project root):
#   pip install -r requirements.txt pyinstaller
#   playwright install chromium
#   pyinstaller build/app.spec
# The finished exe is written to dist/SooqifyImageUpdater.exe
# =========================================================

import os

# SPECPATH is injected by PyInstaller - the directory containing this .spec file (build/).
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
APP_DIR = os.path.join(ROOT, "app")

block_cipher = None

a = Analysis(
    [os.path.join(APP_DIR, "main.py")],
    pathex=[ROOT, APP_DIR],  # APP_DIR so PyInstaller's static analysis can resolve
                              # the app's own top-level sibling imports (config, scanner,
                              # sync_client, uploader, logger_setup).
    binaries=[],
    datas=[
        (os.path.join(APP_DIR, "ui"), os.path.join("app", "ui")),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SooqifyImageUpdater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed app - no terminal window behind the pywebview window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "icon.ico"),
)
