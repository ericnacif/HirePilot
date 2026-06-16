"""Helpers compartilhados pelos arquivos .spec do PyInstaller."""

from __future__ import annotations

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

METADATA_PKGS = ("werkzeug", "flask", "click", "itsdangerous", "jinja2", "markupsafe", "blinker")

WEBVIEW_HIDDEN = [
    "webview",
    "webview.platforms",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr",
]

COMMON_HIDDEN = [
    "flask",
    "jinja2",
    "werkzeug",
    "pdfplumber",
    "docx",
    "httpx",
    "pydantic",
    "pydantic_core",
    *WEBVIEW_HIDDEN,
]

COMMON_EXCLUDES = [
    "torch",
    "sentence_transformers",
    "transformers",
    "tensorflow",
    "matplotlib",
    "pytest",
    "ruff",
]

LITE_EXCLUDES = [*COMMON_EXCLUDES, "playwright"]


def metadata_datas() -> list:
    datas: list = []
    for pkg in METADATA_PKGS:
        try:
            datas += copy_metadata(pkg)
        except Exception:
            pass
    return datas


def app_datas(*, include_playwright: bool = False) -> list:
    datas = [
        ("cv_apply/templates", "cv_apply/templates"),
        ("cv_apply/static", "cv_apply/static"),
    ]
    datas += collect_data_files("webview")
    if include_playwright:
        datas += collect_data_files("playwright")
    datas += metadata_datas()
    return datas


def cv_apply_hiddenimports(*, include_playwright: bool = False) -> list:
    mods = collect_submodules("cv_apply") + collect_submodules("webview")
    extra = list(COMMON_HIDDEN)
    if include_playwright:
        mods += collect_submodules("playwright")
        extra += ["playwright", "playwright.sync_api"]
    return mods + extra
