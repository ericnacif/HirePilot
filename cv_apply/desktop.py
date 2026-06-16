"""Inicialização amigável do VagaMatch como app desktop (.exe).

Abre o navegador automaticamente, escolhe uma porta livre e usa defaults
leves (fontes via API, sem Playwright/torch) para manter o executável enxuto.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import webbrowser

logger = logging.getLogger(__name__)


def _pick_port(start: int = 59000, end: int = 59100) -> int:
    """Primeira porta TCP livre em ``127.0.0.1`` dentro do intervalo."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _ensure_desktop_defaults() -> None:
    """Defaults para o .exe: fontes leves e matching por palavras-chave."""
    os.environ.setdefault("USE_SEMANTIC_MATCHING", "false")
    os.environ.setdefault("SEARCH_SOURCES", "gupy,remotive,remoteok")


def _message_box(title: str, text: str) -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
            return
        except Exception:
            pass
    print(f"\n{title}\n{text}\n", file=sys.stderr)


def run_launch() -> None:
    """Abre o navegador e inicia o servidor Flask local."""
    _ensure_desktop_defaults()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from cv_apply.config import get_settings
    from cv_apply.webapp import _cleanup_stale_uploads, app

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_uploads(settings.data_dir / "uploads")

    host = "127.0.0.1"
    port = _pick_port()
    url = f"http://{host}:{port}"

    def open_browser() -> None:
        time.sleep(1.4)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    print("=" * 54)
    print("  VagaMatch — interface em", url)
    print("  Mantenha esta janela aberta enquanto usa o app.")
    print("  Pressione Ctrl+C ou feche a janela para sair.")
    print("=" * 54)

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except OSError as exc:
        _message_box(
            "VagaMatch",
            "Não foi possível iniciar o servidor.\n\n"
            f"{exc}\n\n"
            "Feche outras instâncias do VagaMatch e tente de novo.",
        )
        raise SystemExit(1) from exc
