# -*- mode: python ; coding: utf-8 -*-
# Gera o executável Windows: pyinstaller vagamatch.spec --noconfirm
# Ou use: build_exe.bat

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = collect_submodules("cv_apply") + [
    "flask",
    "jinja2",
    "werkzeug",
    "pdfplumber",
    "docx",
    "httpx",
    "pydantic",
    "pydantic_core",
]

excludes = [
    "playwright",
    "torch",
    "sentence_transformers",
    "transformers",
    "tensorflow",
    "matplotlib",
    "pytest",
    "ruff",
    "sklearn",
]

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("cv_apply/templates", "cv_apply/templates"),
        ("cv_apply/static", "cv_apply/static"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name="VagaMatch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
