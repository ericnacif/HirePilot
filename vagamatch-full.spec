# -*- mode: python ; coding: utf-8 -*-
# HirePilot Completo — inclui Playwright (LinkedIn/InfoJobs na 1ª execução).

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

block_cipher = None

_METADATA_PKGS = ("werkzeug", "flask", "click", "itsdangerous", "jinja2", "markupsafe", "blinker")


def _pkg_metadata():
    datas = []
    for pkg in _METADATA_PKGS:
        try:
            datas += copy_metadata(pkg)
        except Exception:
            pass
    return datas

hiddenimports = collect_submodules("cv_apply") + collect_submodules("webview") + collect_submodules("playwright") + [
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
    "playwright",
    "playwright.sync_api",
]

excludes = [
    "torch",
    "sentence_transformers",
    "transformers",
    "tensorflow",
    "matplotlib",
    "pytest",
    "ruff",
]

datas = [
    ("cv_apply/templates", "cv_apply/templates"),
    ("cv_apply/static", "cv_apply/static"),
]
datas += collect_data_files("webview")
datas += collect_data_files("playwright")
datas += _pkg_metadata()

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["cv_apply/runtime_hook.py", "cv_apply/runtime_hook_full.py"],
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
    name="HirePilot-Full",
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
