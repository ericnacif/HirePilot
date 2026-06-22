"""Fonte InfoJobs — scraping com contexto Playwright persistente."""

from __future__ import annotations

import logging

from cv_apply.browser_portal import close_portal_context, open_portal_context
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

_BASE = "https://www.infojobs.com.br"


def _infojobs_description(page, url: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1200)
        for sel in (
            ".js_vacancyDescription",
            "[data-testid='vacancy-description']",
            ".ij-Os-block",
            "div.vacancy-description",
        ):
            loc = page.locator(sel).first
            if loc.count():
                text = loc.inner_text(timeout=2500).strip()
                if text:
                    return _strip_html(text)[:5000]
    except Exception as exc:
        logger.debug("InfoJobs descrição %s: %s", url, exc)
    return ""


def _scrape_infojobs(page, keywords: str, cap: int) -> list[JobPosting]:
    slug = _slugify_keywords(keywords)
    page.goto(
        f"{_BASE}/vagas-de-emprego-{slug}.aspx",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    page.wait_for_timeout(4000)

    found: list[JobPosting] = []
    cards = page.locator("div.js_rowCard")
    count = min(cards.count(), cap)
    for i in range(count):
        card = cards.nth(i)
        try:
            href = card.get_attribute("data-href") or ""
            native_id = card.get_attribute("data-id") or href
            title_loc = card.locator("h2.js_vacancyTitle").first
            title = title_loc.inner_text(timeout=2000).strip() if title_loc.count() else ""
            if not title:
                continue
            company = ""
            company_loc = card.locator("a.text-body").first
            if company_loc.count():
                company = company_loc.inner_text(timeout=1500).strip()
            location = ""
            loc_el = card.locator("div.text-medium, span.text-medium").first
            if loc_el.count():
                location = loc_el.inner_text(timeout=1500).strip().split("\n")[0]
            full_url = href if href.startswith("http") else f"{_BASE}{href}"
            found.append(
                JobPosting(
                    id=_make_id("infojobs", str(native_id)),
                    title=title,
                    company=company or "Empresa não informada",
                    location=location,
                    url=full_url,
                    description="",
                    easy_apply=False,
                )
            )
            if len(found) >= cap:
                break
        except Exception as exc:
            logger.debug("InfoJobs card %d erro: %s", i, exc)

    for job in found[: min(len(found), 12)]:
        if not job.description:
            job.description = _infojobs_description(page, job.url)
    return found


def search_infojobs(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    queries = _active_queries(filters)
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    pw = ctx = None
    try:
        pw, ctx, page = open_portal_context(settings, "infojobs")
        for i, query in enumerate(queries):
            if len(jobs) >= max_jobs:
                break
            cap = _fair_cap(
                max_jobs - len(jobs), len(queries) - i,
                floor=5 if filters.broad_mode else 8,
                broad=filters.broad_mode,
            )
            batch: list[JobPosting] = []
            for candidate in _keyword_candidates(query):
                batch = _scrape_infojobs(page, candidate, cap)
                if batch:
                    if candidate != query:
                        logger.info(
                            "InfoJobs: '%s' sem resultados; usando '%s'",
                            query, candidate,
                        )
                    break
            _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("InfoJobs falhou: %s", exc)
    finally:
        close_portal_context(pw, ctx)
    return jobs[:max_jobs]
