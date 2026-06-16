# -*- mode: python ; coding: utf-8 -*-
# Gera o executável Windows: build_exe.bat
# App nativo (janela própria, sem console) via pywebview + WebView2.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hiddenimports = collect_submodules("cv_apply") + collect_submodules("webview") + [
    "flask",
    "jinja2",
    "werkzeug",
    "pdfplumber",
    "docx",
    "httpx",
    "pydantic",
    "pydantic_core",
    "webview",
    "webview.platforms",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr",
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

datas = [
    ("cv_apply/templates", "cv_apply/templates"),
    ("cv_apply/static", "cv_apply/static"),
]
datas += collect_data_files("webview")

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
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
    name="HirePilot",
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
)
