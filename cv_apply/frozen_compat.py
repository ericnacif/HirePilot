"""Compatibilidade com executável PyInstaller (metadados, instância única)."""

from __future__ import annotations

import sys


def apply_frozen_patches() -> None:
    if not getattr(sys, "frozen", False):
        return
    _patch_importlib_metadata()


def _patch_importlib_metadata() -> None:
    import importlib.metadata as md

    if getattr(md, "_hirepilot_patched", False):
        return

    _orig_version = md.version

    def _safe_version(name: str) -> str:
        try:
            return _orig_version(name)
        except md.PackageNotFoundError:
            return "0.0.0"

    md.version = _safe_version  # type: ignore[method-assign]
    md._hirepilot_patched = True  # type: ignore[attr-defined]


def ensure_single_instance() -> bool:
    """Retorna False se outra instância do app já estiver em execução (Windows)."""
    if not sys.platform.startswith("win"):
        return True

    import ctypes

    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, True, "Global\\HirePilot_SingleInstance")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(mutex)
        return False
    return True
