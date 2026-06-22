"""Fonte Trabalha Brasil — scraping da busca (Playwright)."""

from __future__ import annotations

import logging
import re

from cv_apply.browser_portal import close_portal_context, open_portal_context
from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.sources import (
    _active_queries,
    _append_unique,
    _fair_cap,
    _keyword_candidates,
    _make_id,
    _strip_html,
)

logger = logging.getLogger(__name__)

_BASE = "https://trabalhabrasil.com.br"


def _parse_card(link) -> JobPosting | None:
    href = (link.get_attribute("href") or "").strip()
    if not href or "/vaga/" not in href and "/vagas/" not in href:
        return None
    title = (link.get_attribute("title") or link.inner_text(timeout=2000) or "").strip()
    title = re.sub(r"\s+", " ", title)
    if len(title) < 3:
        return None
    native = href.rstrip("/").split("/")[-1]
    url = href if href.startswith("http") else f"{_BASE}{href}"
    return JobPosting(
        id=_make_id("trabalhabrasil", native),
        title=title,
        company="Empresa não informada",
        location="Brasil",
        url=url,
        description="",
        easy_apply=False,
    )


def _scrape(page, keywords: str, cap: int) -> list[JobPosting]:
    q = (keywords or "desenvolvedor").strip().replace(" ", "+")
    page.goto(f"{_BASE}/busca?palavra={q}", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(5000)
    found: list[JobPosting] = []
    seen: set[str] = set()
    for sel in ('a[href*="/vaga/"]', 'a[href*="/vagas/"]', "article a"):
        links = page.locator(sel)
        for i in range(min(links.count(), cap * 3)):
            if len(found) >= cap:
                break
            try:
                link = links.nth(i)
                href = link.get_attribute("href") or ""
                if href in seen:
                    continue
                seen.add(href)
                job = _parse_card(link)
                if job:
                    found.append(job)
            except Exception:
                continue
        if found:
            break
    return found


def search_trabalhabrasil(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    queries = _active_queries(filters)
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    pw = ctx = None
    try:
        pw, ctx, page = open_portal_context(settings, "trabalhabrasil")
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
                batch = _scrape(page, candidate, cap)
                if batch:
                    break
            _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Trabalha Brasil falhou: %s", exc)
    finally:
        close_portal_context(pw, ctx)
    return jobs[:max_jobs]
