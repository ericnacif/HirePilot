"""Fonte Catho — scraping da busca via Playwright (contexto persistente)."""

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

_BASE = "https://www.catho.com.br"
_LOGIN_URL = f"{_BASE}/signin/"


def _catho_blocked(page) -> bool:
    title = (page.title() or "").lower()
    return "inválida" in title or "invalida" in title


def _catho_logged_in(page) -> bool:
    if _catho_blocked(page):
        return False
    url = (page.url or "").lower()
    if "/signin" in url or "/cadastro" in url:
        return False
    body = page.inner_text("body").lower()
    if "cadastre-se agora para visualizar todas" in body:
        return False
    try:
        cookies = page.context.cookies(_BASE)
        for c in cookies:
            if c.get("name") in {"catho_session", "session", "auth_token", "user_logged"}:
                if c.get("value"):
                    return True
    except Exception:
        pass
    if page.locator('a[href*="/signin"]').count() == 0:
        return True
    if page.locator('[class*="avatar"], [data-testid="user-menu"]').count():
        return True
    return False


def _parse_card(article) -> JobPosting | None:
    link = article.locator("h2.title_offer a").first
    if not link.count():
        link = article.locator('a[href*="/vagas/"]').first
    if not link.count():
        return None

    href = (link.get_attribute("href") or "").strip()
    title = link.inner_text(timeout=2000).strip()
    if not href or not title:
        return None
    if re.search(r"/vagas/[^/]+/?$", href) and not re.search(r"/\d+", href):
        return None

    native_id = href.rstrip("/").split("/")[-1]
    if not native_id.isdigit():
        match = re.search(r"/(\d+)/?$", href)
        native_id = match.group(1) if match else href

    company = ""
    company_loc = article.locator("p span.text-12").first
    if company_loc.count():
        company = company_loc.inner_text(timeout=1500).strip()

    location = ""
    loc_loc = article.locator("p:has(span.i_job_location)").first
    if loc_loc.count():
        location = loc_loc.inner_text(timeout=1500).strip()
        location = re.sub(r"\s+", " ", location)

    full_url = href if href.startswith("http") else f"{_BASE}{href}"
    return JobPosting(
        id=_make_id("catho", str(native_id)),
        title=title,
        company=company or "Empresa não informada",
        location=location,
        url=full_url,
        description="",
        easy_apply=False,
    )


def _catho_description(page, url: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1200)
        for sel in (
            ".description_vacancy",
            "[data-testid='job-description']",
            ".job-description",
            "section.description",
        ):
            loc = page.locator(sel).first
            if loc.count():
                text = loc.inner_text(timeout=2500).strip()
                if text:
                    return _strip_html(text)[:5000]
    except Exception as exc:
        logger.debug("Catho descrição %s: %s", url, exc)
    return ""


def _collect_page_cards(page, cap: int, found: list[JobPosting], seen_ids: set[str]) -> None:
    cards = page.locator("article")
    count = cards.count()
    for i in range(count):
        if len(found) >= cap:
            return
        try:
            job = _parse_card(cards.nth(i))
            if job and job.id not in seen_ids:
                seen_ids.add(job.id)
                found.append(job)
        except Exception as exc:
            logger.debug("Catho card %d erro: %s", i, exc)


def _scrape_catho(page, keywords: str, cap: int, *, logged_in: bool) -> list[JobPosting]:
    slug = _slugify_keywords(keywords)
    base_url = f"{_BASE}/vagas/{slug}/"
    found: list[JobPosting] = []
    seen_ids: set[str] = set()
    max_pages = 4 if logged_in else 2

    for page_num in range(1, max_pages + 1):
        if len(found) >= cap:
            break
        url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)

        if _catho_blocked(page):
            logger.warning(
                "Catho bloqueou o acesso (Akamai). Use HEADLESS=false e busque uma vez "
                "para validar a sessão em browser_data/catho."
            )
            break

        before = len(found)
        _collect_page_cards(page, cap, found, seen_ids)
        if len(found) == before:
            break

    for job in found[: min(len(found), 10)]:
        if not job.description:
            job.description = _catho_description(page, job.url)

    return found


def search_catho(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    queries = _active_queries(filters)
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    pw = ctx = None

    try:
        pw, ctx, page = open_portal_context(settings, "catho", force_visible=True)
        logged_in = _catho_logged_in(page)
        if not logged_in:
            logged_in = wait_for_portal_login(
                page,
                login_url=_LOGIN_URL,
                is_logged_in=lambda: _catho_logged_in(page),
                portal_label="Catho",
                timeout_seconds=180,
            )
        if not logged_in:
            logger.info("Catho: busca sem login (preview limitado a ~20 vagas/página).")

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
                batch = _scrape_catho(page, candidate, cap, logged_in=logged_in)
                if batch:
                    if candidate != query:
                        logger.info(
                            "Catho: '%s' sem resultados; usando '%s'",
                            query,
                            candidate,
                        )
                    break
            _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Catho falhou: %s", exc)
    finally:
        close_portal_context(pw, ctx)

    return jobs[:max_jobs]
