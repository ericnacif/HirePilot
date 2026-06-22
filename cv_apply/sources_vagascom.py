"""Fonte Vagas.com — scraping autenticado via Playwright (contexto persistente)."""

from __future__ import annotations

import logging
import re

from cv_apply.browser_portal import (
    close_portal_context,
    open_portal_context,
    wait_for_portal_login,
)
from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.sources import (
    _active_queries,
    _append_unique,
    _fair_cap,
    _keyword_candidates,
    _make_id,
    _slugify_keywords,
    _strip_html,
)

logger = logging.getLogger(__name__)

_BASE = "https://www.vagas.com.br"
_LOGIN_URL = f"{_BASE}/login-candidatos"


def _vagascom_logged_in(page) -> bool:
    url = (page.url or "").lower()
    if "login-candidatos" in url:
        return False
    if page.locator('input[name="login_candidatos_form[usuario]"]').count():
        return False
    if page.locator('a[href*="/vaga/"]').count() > 0:
        return True
    if page.locator('a[href*="logout"], a[href*="sair"]').count():
        return True
    body = page.inner_text("body").lower()
    return "minha conta" in body or "meu currículo" in body


def _parse_vaga_link(link) -> JobPosting | None:
    href = (link.get_attribute("href") or "").strip()
    if not href or "/vaga/" not in href:
        return None

    title = (link.get_attribute("title") or link.inner_text(timeout=2000) or "").strip()
    title = re.sub(r"\s+", " ", title)
    if not title or len(title) < 3:
        return None

    native_id = href.rstrip("/").split("/")[-1]
    full_url = href if href.startswith("http") else f"{_BASE}{href}"

    company = ""
    location = ""
    try:
        container = link.locator("xpath=ancestor::article[1] | ancestor::li[1] | ancestor::div[contains(@class,'vaga')][1]").first
        if container.count():
            text = container.inner_text(timeout=2000)
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            for ln in lines:
                if ln == title:
                    continue
                if not company and ln and ln.lower() not in {"candidatar-se", "ver vaga"}:
                    company = ln
                    continue
                if company and not location and (" - " in ln or re.search(r"\b[A-Z]{2}\b", ln)):
                    location = ln
                    break
    except Exception:
        pass

    return JobPosting(
        id=_make_id("vagascom", native_id),
        title=title,
        company=company or "Empresa não informada",
        location=location,
        url=full_url,
        description="",
        easy_apply=False,
    )


def _vagascom_description(page, url: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1200)
        for sel in (
            ".descricao",
            ".job-description",
            "[data-testid='job-description']",
            "#descricaoVaga",
            ".vaga-descricao",
        ):
            loc = page.locator(sel).first
            if loc.count():
                text = loc.inner_text(timeout=2500).strip()
                if text:
                    return _strip_html(text)[:5000]
    except Exception as exc:
        logger.debug("Vagas.com descrição %s: %s", url, exc)
    return ""


def _scrape_vagascom(page, keywords: str, cap: int) -> list[JobPosting]:
    slug = _slugify_keywords(keywords)
    page.goto(
        f"{_BASE}/vagas-de-emprego/{slug}",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    page.wait_for_timeout(4000)

    for _ in range(2):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(800)

    body = page.inner_text("body")
    if "Não encontramos" in body and page.locator('a[href*="/vaga/"]').count() == 0:
        return []

    found: list[JobPosting] = []
    seen_urls: set[str] = set()

    card_selectors = [
        "li.vaga",
        "div.vaga",
        "article.vaga",
        '[class*="resultado"]',
        '[data-testid*="job"]',
    ]
    for sel in card_selectors:
        cards = page.locator(sel)
        if cards.count():
            for i in range(min(cards.count(), cap * 2)):
                if len(found) >= cap:
                    break
                card = cards.nth(i)
                link = card.locator('a[href*="/vaga/"]').first
                if not link.count():
                    continue
                try:
                    href = link.get_attribute("href") or ""
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    job = _parse_vaga_link(link)
                    if job:
                        found.append(job)
                except Exception as exc:
                    logger.debug("Vagas.com card %d: %s", i, exc)
            if found:
                break

    if not found:
        links = page.locator('a[href*="/vaga/"]')
        count = links.count()
        for i in range(count):
            if len(found) >= cap:
                break
            try:
                link = links.nth(i)
                href = link.get_attribute("href") or ""
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                job = _parse_vaga_link(link)
                if job:
                    found.append(job)
            except Exception as exc:
                logger.debug("Vagas.com link %d erro: %s", i, exc)

    for job in found[: min(len(found), 8)]:
        if not job.description:
            job.description = _vagascom_description(page, job.url)

    return found


def search_vagascom(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    queries = _active_queries(filters)
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    pw = ctx = None

    try:
        pw, ctx, page = open_portal_context(settings, "vagascom", force_visible=True)
        if not wait_for_portal_login(
            page,
            login_url=_LOGIN_URL,
            is_logged_in=lambda: _vagascom_logged_in(page),
            portal_label="Vagas.com",
        ):
            logger.warning("Vagas.com: login não concluído.")
            return []

        for i, query in enumerate(queries):
            if len(jobs) >= max_jobs:
                break
            cap = _fair_cap(
                max_jobs - len(jobs),
                len(queries) - i,
                floor=5 if filters.broad_mode else 8,
                broad=filters.broad_mode,
            )
            batch: list[JobPosting] = []
            for candidate in _keyword_candidates(query):
                batch = _scrape_vagascom(page, candidate, cap)
                if batch:
                    if candidate != query:
                        logger.info(
                            "Vagas.com: '%s' sem resultados; usando '%s'",
                            query,
                            candidate,
                        )
                    break
            _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Vagas.com falhou: %s", exc)
    finally:
        close_portal_context(pw, ctx)

    return jobs[:max_jobs]
