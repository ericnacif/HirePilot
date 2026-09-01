# -*- mode: python ; coding: utf-8 -*-
# Vaga em Vista Leve — build_exe.bat / release workflow

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH)))

from build_support.pyinstaller_common import LITE_EXCLUDES, app_datas, cv_apply_hiddenimports

block_cipher = None

datas = app_datas()
hiddenimports = cv_apply_hiddenimports()

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["cv_apply/runtime_hook.py"],
    excludes=LITE_EXCLUDES,
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
    name="Vaga em Vista",
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
    icon="cv_apply/static/icon.ico",
)
