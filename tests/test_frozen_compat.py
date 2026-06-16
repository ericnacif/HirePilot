"""Testes de compatibilidade com executável congelado."""

from __future__ import annotations

import importlib.metadata

from cv_apply.frozen_compat import _patch_importlib_metadata


def test_patch_importlib_metadata_handles_missing_package():
    _patch_importlib_metadata()
    assert importlib.metadata.version("pacote-inexistente-xyz") == "0.0.0"
