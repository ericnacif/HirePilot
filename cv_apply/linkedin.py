"""Automação assistida no LinkedIn via Playwright."""

from __future__ import annotations

import hashlib
import logging
import random
import re
import time
from typing import Callable, Optional
from urllib.parse import urlencode

from playwright.sync_api import BrowserContext, Page, sync_playwright

from cv_apply.config import Settings
from cv_apply.profile import JobPosting

logger = logging.getLogger(__name__)

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/"


def _human_delay(min_s: float = 1.5, max_s: float = 3.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _job_id_from_url(url: str) -> str:
    match = re.search(r"currentJobId=(\d+)", url) or re.search(r"/jobs/view/(\d+)", url)
    if match:
        return match.group(1)
    return hashlib.md5(url.encode()).hexdigest()[:12]


class LinkedInClient:
    """Cliente Playwright para busca e Easy Apply assistido."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.browser_data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def __enter__(self) -> "LinkedInClient":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    def start(self) -> None:
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.settings.browser_data_dir),
            headless=self.settings.headless,
            viewport={"width": 1280, "height": 900},
            locale="pt-BR",
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    def stop(self) -> None:
        if self._context:
            self._context.close()
        if self._playwright:
            self._playwright.stop()
        self._context = None
        self._page = None
        self._playwright = None

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Cliente LinkedIn não iniciado. Use start() ou context manager.")
        return self._page

    def ensure_logged_in(self, timeout_seconds: int = 300) -> bool:
        """Abre LinkedIn e aguarda login manual se necessário."""
        self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        _human_delay(2, 4)

        if self._is_logged_in():
            logger.info("Sessão LinkedIn ativa.")
            return True

        print("\n" + "=" * 60)
        print(">>> Faça login no LinkedIn na janela do navegador que abriu.")
        print(">>> A detecção é automática assim que o login for concluído.")
        print(f">>> Aguardando até {timeout_seconds}s...")
        print("=" * 60 + "\n")

        deadline = time.time() + timeout_seconds
        last_notice = 0.0
        while time.time() < deadline:
            if self._is_logged_in():
                print(">>> Login detectado! Continuando...\n")
                logger.info("Login detectado.")
                _human_delay(1, 2)
                return True

            remaining = int(deadline - time.time())
            if time.time() - last_notice >= 15:
                print(f"    ...aguardando login ({remaining}s restantes)")
                last_notice = time.time()
            time.sleep(2)

        logger.warning("Timeout aguardando login.")
        return False

    def _is_logged_in(self) -> bool:
        # Forma mais confiavel: cookie de sessao do LinkedIn (li_at)
        try:
            cookies = self._context.cookies("https://www.linkedin.com")
            for cookie in cookies:
                if cookie.get("name") == "li_at" and cookie.get("value"):
                    return True
        except Exception:
            pass

        url = self.page.url
        if "/login" in url or "/checkpoint" in url or "/authwall" in url:
            return False

        try:
            selectors = (
                "img.global-nav__me-photo, "
                "button.global-nav__primary-link-me-menu-trigger, "
                "div.global-nav__me, "
                "[data-control-name='nav.settings']"
            )
            return self.page.locator(selectors).count() > 0
        except Exception:
            return "feed" in url or "jobs" in url

    def build_search_url(self) -> str:
        from cv_apply.filters import SearchFilters

        params = {
            "keywords": self.settings.search_keywords,
            "location": self.settings.search_location,
        }
        filters = SearchFilters.from_settings(self.settings)
        params.update(filters.linkedin_params())
        return f"{LINKEDIN_JOBS_URL}?{urlencode(params)}"

    def search_jobs(self, max_jobs: int = 25) -> list[JobPosting]:
        """Busca vagas e coleta informações dos cards."""
        if not self.ensure_logged_in():
            raise RuntimeError("Não foi possível confirmar login no LinkedIn.")

        url = self.build_search_url()
        logger.info("Buscando vagas: %s", url)
        self.page.goto(url, wait_until="domcontentloaded")
        _human_delay(3, 5)

        self._scroll_job_list(max_scrolls=5)
        jobs = self._collect_job_cards(max_jobs)

        for i, job in enumerate(jobs):
            logger.info("Coletando descrição %d/%d: %s", i + 1, len(jobs), job.title)
            description = self._fetch_job_description(job.url)
            job.description = description
            _human_delay(1.5, 3)

        return jobs

    def _scroll_job_list(self, max_scrolls: int = 5) -> None:
        for _ in range(max_scrolls):
            self.page.evaluate(
                """() => {
                    const list = document.querySelector('.jobs-search-results-list, .scaffold-layout__list');
                    if (list) list.scrollTop = list.scrollHeight;
                }"""
            )
            _human_delay(1, 2)

    def _collect_job_cards(self, max_jobs: int) -> list[JobPosting]:
        selectors = [
            "li.scaffold-layout__list-item",
            "div.job-card-container",
            "ul.jobs-search__results-list li",
        ]
        cards = None
        for sel in selectors:
            loc = self.page.locator(sel)
            if loc.count() > 0:
                cards = loc
                break

        if not cards or cards.count() == 0:
            logger.warning("Nenhum card de vaga encontrado. Seletores podem ter mudado.")
            return []

        jobs: list[JobPosting] = []
        count = min(cards.count(), max_jobs)

        for i in range(count):
            card = cards.nth(i)
            try:
                card.click()
                _human_delay(1, 2)

                title = self._safe_text([
                    "a.job-card-list__title",
                    "a.job-card-container__link",
                    ".job-details-jobs-unified-top-card__job-title",
                    "h1.t-24",
                ])
                company = self._safe_text([
                    ".job-card-container__company-name",
                    ".job-details-jobs-unified-top-card__company-name",
                    "a.job-card-container__company-name",
                ])
                location = self._safe_text([
                    ".job-card-container__metadata-item",
                    ".job-details-jobs-unified-top-card__bullet",
                ])
                job_url = self.page.url
                easy_apply = self._has_easy_apply()

                if not title:
                    continue

                job = JobPosting(
                    id=_job_id_from_url(job_url),
                    title=title,
                    company=company or "Empresa não informada",
                    location=location or "",
                    url=job_url,
                    easy_apply=easy_apply,
                )
                jobs.append(job)
            except Exception as exc:
                logger.debug("Erro ao ler card %d: %s", i, exc)

        return jobs

    def _safe_text(self, selectors: list[str]) -> str:
        for sel in selectors:
            loc = self.page.locator(sel).first
            if loc.count() > 0:
                text = loc.inner_text(timeout=2000).strip()
                if text:
                    return text.split("\n")[0].strip()
        return ""

    def _has_easy_apply(self) -> bool:
        selectors = [
            "button.jobs-apply-button:has-text('Candidatura')",
            "button.jobs-apply-button:has-text('Easy Apply')",
            "button:has-text('Candidatura simplificada')",
        ]
        for sel in selectors:
            if self.page.locator(sel).count() > 0:
                return True
        return False

    def _fetch_job_description(self, url: str) -> str:
        if self.page.url != url:
            self.page.goto(url, wait_until="domcontentloaded")
            _human_delay(2, 3)

        selectors = [
            ".jobs-description__content",
            "#job-details",
            ".jobs-box__html-content",
            "article.jobs-description__container",
        ]
        for sel in selectors:
            loc = self.page.locator(sel).first
            if loc.count() > 0:
                try:
                    return loc.inner_text(timeout=5000).strip()
                except Exception:
                    pass
        return ""

    def prepare_easy_apply(
        self,
        job: JobPosting,
        cover_letter: str = "",
        on_step: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Abre Easy Apply e pré-preenche campos quando possível.
        PARA antes de clicar em Enviar — o usuário confirma manualmente.
        """
        if not self.ensure_logged_in():
            return False

        self.page.goto(job.url, wait_until="domcontentloaded")
        _human_delay(2, 4)

        apply_selectors = [
            "button.jobs-apply-button:has-text('Candidatura')",
            "button.jobs-apply-button:has-text('Easy Apply')",
            "button:has-text('Candidatura simplificada')",
        ]
        clicked = False
        for sel in apply_selectors:
            btn = self.page.locator(sel).first
            if btn.count() > 0:
                btn.click()
                clicked = True
                break

        if not clicked:
            logger.warning("Botão Easy Apply não encontrado para: %s", job.title)
            if on_step:
                on_step("Easy Apply não disponível nesta vaga.")
            return False

        _human_delay(2, 3)
        if on_step:
            on_step("Modal Easy Apply aberto.")

        self._fill_easy_apply_steps(cover_letter, on_step)

        print("\n" + "=" * 60)
        print("MODO ASSISTIDO: Revise os campos e clique em ENVIAR manualmente.")
        print("Pressione ENTER aqui no terminal quando terminar (enviado ou cancelado).")
        print("=" * 60 + "\n")
        input()

        return True

    def _fill_easy_apply_steps(
        self,
        cover_letter: str,
        on_step: Optional[Callable[[str], None]] = None,
    ) -> None:
        max_steps = 8
        for step in range(max_steps):
            _human_delay(1, 2)
            self._try_fill_textareas(cover_letter)
            self._try_upload_resume()
            self._try_select_dropdowns()

            if on_step:
                on_step(f"Passo {step + 1}: campos pré-preenchidos quando possível.")

            next_selectors = [
                "button[aria-label='Continue to next step']",
                "button[aria-label='Review your application']",
                "button:has-text('Avançar')",
                "button:has-text('Próximo')",
                "button:has-text('Review')",
            ]
            submit_selectors = [
                "button[aria-label='Submit application']",
                "button:has-text('Enviar candidatura')",
                "button:has-text('Submit application')",
            ]

            for sel in submit_selectors:
                if self.page.locator(sel).count() > 0:
                    if on_step:
                        on_step("Tela final detectada. NÃO enviando automaticamente.")
                    return

            advanced = False
            for sel in next_selectors:
                btn = self.page.locator(sel).first
                if btn.count() > 0 and btn.is_enabled():
                    btn.click()
                    advanced = True
                    _human_delay(1.5, 2.5)
                    break

            if not advanced:
                break

    def _try_fill_textareas(self, cover_letter: str) -> None:
        if not cover_letter:
            return
        textareas = self.page.locator("textarea")
        for i in range(textareas.count()):
            ta = textareas.nth(i)
            try:
                current = ta.input_value()
                if not current.strip():
                    ta.fill(cover_letter[:2000])
            except Exception:
                pass

    def _try_upload_resume(self) -> None:
        resume = self.settings.resume_path
        if not resume.exists():
            return
        file_inputs = self.page.locator("input[type='file']")
        for i in range(file_inputs.count()):
            try:
                file_inputs.nth(i).set_input_files(str(resume))
                _human_delay(0.5, 1)
            except Exception:
                pass

    def _try_select_dropdowns(self) -> None:
        selects = self.page.locator("select")
        for i in range(selects.count()):
            sel = selects.nth(i)
            try:
                options = sel.locator("option")
                if options.count() > 1:
                    value = options.nth(1).get_attribute("value")
                    if value:
                        sel.select_option(value=value)
            except Exception:
                pass
