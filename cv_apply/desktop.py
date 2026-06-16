"""App desktop do HirePilot — janela nativa, sem console nem navegador externo.

No Windows usa WebView2 (Edge embutido): duplo clique abre uma janela do app
com a interface dentro. O servidor Flask roda em segundo plano na mesma
máquina.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from werkzeug.serving import BaseWSGIServer

logger = logging.getLogger(__name__)

_WINDOW_TITLE = "HirePilot"
_WINDOW_SIZE = (1280, 860)
_WINDOW_MIN = (960, 640)

_SPLASH_HTML = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{height:100vh;display:flex;align-items:center;justify-content:center;
    font-family:Segoe UI,system-ui,sans-serif;background:#F6F8FC;color:#1A2030}
  .box{text-align:center;padding:28px}
  .logo{width:58px;height:58px;margin:0 auto 16px;border-radius:16px;
    background:linear-gradient(145deg,#fff,#F6F8FC);border:1px solid rgba(93,140,255,.2);
    box-shadow:0 10px 28px rgba(93,140,255,.18);display:flex;align-items:center;justify-content:center;
    font-size:28px;animation:pulse 1.4s ease-in-out infinite}
  h1{font-size:22px;font-weight:700;margin-bottom:6px;color:#1A2030}
  p{font-size:13px;color:#64748b;margin-bottom:18px}
  .bar{width:200px;height:5px;border-radius:99px;background:rgba(93,140,255,.15);margin:0 auto;overflow:hidden}
  .bar i{display:block;height:100%;width:40%;background:linear-gradient(90deg,#5D8CFF,#8FB0FF);
    animation:slide 1s ease-in-out infinite}
  @keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
  @keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
</style></head><body><div class="box"><div class="logo">✈</div>
<h1>HirePilot</h1><p id="msg">Iniciando…</p><div class="bar"><i></i></div></div></body></html>"""


def _is_full_variant() -> bool:
    return os.getenv("HIREPILOT_FULL", "").lower() in {"1", "true", "yes"}


def _ensure_desktop_defaults() -> None:
    os.environ.setdefault("USE_SEMANTIC_MATCHING", "false")
    if _is_full_variant():
        os.environ.setdefault(
            "SEARCH_SOURCES",
            "gupy,indeed,greenhouse,remotive,remoteok,infojobs,linkedin",
        )
    else:
        os.environ.setdefault("SEARCH_SOURCES", "gupy,indeed,greenhouse,remotive,remoteok")


def _bootstrap_playwright_async(data_dir) -> None:
    """Baixa Chromium uma vez (variante Completa) em segundo plano."""
    if not _is_full_variant():
        return
    browser_dir = data_dir / "playwright-browsers"
    browser_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)

    def _run() -> None:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                path = p.chromium.executable_path
                if path and os.path.isfile(path):
                    return
        except Exception:
            pass
        try:
            import subprocess

            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=False,
                capture_output=True,
                timeout=600,
            )
            logger.info("Playwright Chromium instalado em %s", browser_dir)
        except Exception as exc:
            logger.warning("Falha ao instalar Playwright: %s", exc)

    threading.Thread(target=_run, name="playwright-bootstrap", daemon=True).start()


def _pick_port(start: int = 59000, end: int = 59100) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _message_box(title: str, text: str, *, error: bool = True) -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes

            flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
            ctypes.windll.user32.MessageBoxW(0, text, title, flags)
            return
        except Exception:
            pass
    stream = sys.stderr if error else sys.stdout
    print(f"\n{title}\n{text}\n", file=stream)


def _wait_for_server(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.12)
    return False


def _start_flask(host: str, port: int) -> tuple[BaseWSGIServer, threading.Thread]:
    from werkzeug.serving import make_server

    from cv_apply.webapp import app

    server = make_server(host, port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, name="vagamatch-http", daemon=True)
    thread.start()
    return server, thread


def _run_native_window(url: str) -> None:
    import webview

    window = webview.create_window(
        _WINDOW_TITLE,
        html=_SPLASH_HTML,
        width=420,
        height=300,
        resizable=True,
        min_size=_WINDOW_MIN,
        text_select=True,
    )

    def _open_app() -> None:
        time.sleep(0.45)
        window.load_url(url)
        try:
            window.resize(_WINDOW_SIZE[0], _WINDOW_SIZE[1])
        except Exception:
            pass

    backends: tuple[str | None, ...] = ("edgechromium", "mshtml") if sys.platform.startswith("win") else (None,)
    last_exc: Exception | None = None
    for gui in backends:
        try:
            if gui:
                webview.start(_open_app, gui=gui)
            else:
                webview.start(_open_app)
            return
        except Exception as exc:
            last_exc = exc
            logger.warning("Janela nativa (%s) indisponível: %s", gui or "default", exc)
    raise last_exc or RuntimeError("Não foi possível abrir a janela do app")


def _run_browser_fallback(url: str) -> None:
    _message_box(
        _WINDOW_TITLE,
        "Abrindo no navegador padrão.\n\n"
        "Para a janela nativa do app, instale o WebView2 Runtime da Microsoft "
        "(comum no Windows 10/11).",
        error=False,
    )
    webbrowser.open(url)
    _message_box(
        _WINDOW_TITLE,
        "O HirePilot está rodando no navegador.\n\nClique em OK para encerrar o app.",
        error=False,
    )


def _start_alert_scheduler(settings) -> None:
    """Verifica alertas de vagas a cada 30 minutos (app desktop)."""
    from cv_apply.alert_scheduler import start_alert_scheduler

    def _notify(hits: list[dict]) -> None:
        total = sum(h["new_count"] for h in hits)
        _message_box(
            _WINDOW_TITLE,
            f"Alertas HirePilot: {total} vaga(s) nova(s) encontrada(s).\n\n"
            "Abra o app para ver os detalhes.",
            error=False,
        )

    start_alert_scheduler(settings.data_dir, on_hits=_notify)


def run_launch() -> None:
    """Inicia o HirePilot como app desktop."""
    _ensure_desktop_defaults()
    logging.basicConfig(level=logging.WARNING)

    from cv_apply.config import get_settings
    from cv_apply.webapp import _cleanup_stale_uploads

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_uploads(settings.data_dir / "uploads")
    _bootstrap_playwright_async(settings.data_dir)

    host = "127.0.0.1"
    port = _pick_port()
    url = f"http://{host}:{port}"

    try:
        server, _thread = _start_flask(host, port)
    except OSError as exc:
        _message_box(
            _WINDOW_TITLE,
            "Não foi possível iniciar o servidor.\n\n"
            f"{exc}\n\n"
            "Feche outras instâncias do HirePilot e tente de novo.",
        )
        raise SystemExit(1) from exc

    if not _wait_for_server(url):
        server.shutdown()
        _message_box(
            _WINDOW_TITLE,
            "O servidor demorou demais para responder.\n\nTente abrir o app de novo.",
        )
        raise SystemExit(1)

    _start_alert_scheduler(settings)

    use_browser = os.getenv("VAGAMATCH_BROWSER", "").lower() in {"1", "true", "yes"}
    try:
        if use_browser:
            _run_browser_fallback(url)
        else:
            _run_native_window(url)
    except Exception as exc:
        logger.warning("Janela nativa indisponível (%s); usando navegador.", exc)
        _run_browser_fallback(url)
    finally:
        server.shutdown()
