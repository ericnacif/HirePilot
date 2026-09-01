#!/usr/bin/env python3
"""Ponto de entrada do executável Vaga em Vista (PyInstaller)."""

from cv_apply.frozen_compat import apply_frozen_patches, ensure_single_instance

apply_frozen_patches()

if __name__ == "__main__":
    if not ensure_single_instance():
        from cv_apply.desktop import _WINDOW_TITLE, _message_box

        _message_box(
            _WINDOW_TITLE,
            "O Vaga em Vista já está aberto.\n\nFeche a outra janela antes de abrir de novo.",
            error=False,
        )
        raise SystemExit(0)

    from cv_apply.desktop import run_launch

    run_launch()
