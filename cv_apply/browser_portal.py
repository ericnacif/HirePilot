"""Contexto Playwright persistente para portais BR (Catho, Vagas.com)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from cv_apply.config import Settings

logger = logging.getLogger(__name__)

# Akamai da Catho bloqueia modo headless — exige navegador visível na 1ª sessão.
PORTALS_REQUIRING_VISIBLE_BROWSER = frozenset({"catho", "vagascom"})


def portal_data_dir(settings: Settings, name: str) -> Path:
    path = settings.browser_data_dir / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def open_portal_context(
    settings: Settings,
    name: str,
    *,
    force_visible: bool = False,
) -> tuple[Playwright, BrowserContext, Page]:
    """Abre contexto persistente isolado por portal (cookies/sessão reutilizados)."""
    pw = sync_playwright().start()
    headless = (
        settings.headless
        and not force_visible
        and name not in PORTALS_REQUIRING_VISIBLE_BROWSER
    )
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(portal_data_dir(settings, name)),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        locale="pt-BR",
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw, ctx, page


def close_portal_context(pw: Playwright | None, ctx: BrowserContext | None) -> None:
    if ctx:
        ctx.close()
    if pw:
        pw.stop()


def wait_for_portal_login(
    page: Page,
    *,
    login_url: str,
    is_logged_in: Callable[[], bool],
    portal_label: str,
    timeout_seconds: int = 300,
) -> bool:
    """Aguarda login manual na janela do navegador."""
    page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
    time.sleep(2)
    if is_logged_in():
        logger.info("Sessão %s ativa.", portal_label)
        return True

    print("\n" + "=" * 60)
    print(f">>> Faça login no {portal_label} na janela do navegador que abriu.")
    print(">>> A detecção é automática assim que o login for concluído.")
    print(f">>> Aguardando até {timeout_seconds}s...")
    print("=" * 60 + "\n")

    deadline = time.time() + timeout_seconds
    last_notice = 0.0
    while time.time() < deadline:
        if is_logged_in():
            print(f">>> Login no {portal_label} detectado! Continuando...\n")
            logger.info("Login %s detectado.", portal_label)
            return True
        remaining = int(deadline - time.time())
        if time.time() - last_notice >= 15:
            print(f"    ...aguardando login no {portal_label} ({remaining}s restantes)")
            last_notice = time.time()
        time.sleep(2)

    logger.warning("Timeout aguardando login no %s.", portal_label)
    return False
