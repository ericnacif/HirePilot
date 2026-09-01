# -*- mode: python ; coding: utf-8 -*-
# Vaga em Vista Completo — Playwright (LinkedIn/InfoJobs)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH)))

from build_support.pyinstaller_common import COMMON_EXCLUDES, app_datas, cv_apply_hiddenimports

block_cipher = None

datas = app_datas(include_playwright=True)
hiddenimports = cv_apply_hiddenimports(include_playwright=True)

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["cv_apply/runtime_hook.py", "cv_apply/runtime_hook_full.py"],
    excludes=COMMON_EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Vaga em Vista-Full",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="cv_apply/static/icon.ico",
)
