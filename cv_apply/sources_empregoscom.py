"""Fonte Empregos.com.br — scraping leve da busca."""

from __future__ import annotations

import logging
import re

import httpx

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

_BASE = "https://www.empregos.com.br"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def _parse_html(html: str, cap: int) -> list[JobPosting]:
    found: list[JobPosting] = []
    pattern = re.compile(
        r'href="(?P<href>/[^"]*(?:vaga|emprego)[^"]*)"[^>]*>(?P<title>[^<]{4,120})',
        re.I,
    )
    seen: set[str] = set()
    for m in pattern.finditer(html):
        href = m.group("href")
        if href in seen or "css" in href or "javascript" in href:
            continue
        seen.add(href)
        title = _strip_html(m.group("title"))
        if not title or len(title) < 4:
            continue
        native = href.rstrip("/").split("/")[-1][:40]
        url = href if href.startswith("http") else f"{_BASE}{href}"
        found.append(
            JobPosting(
                id=_make_id("empregoscom", native),
                title=title,
                company="Empresa não informada",
                location="Brasil",
                url=url,
                description="",
                easy_apply=False,
            )
        )
        if len(found) >= cap:
            break
    return found


def search_empregoscom(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    queries = _active_queries(filters)
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    try:
        with httpx.Client(timeout=30, headers=_HEADERS, follow_redirects=True) as client:
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
                    slug = _slugify_keywords(candidate)
                    for path in (
                        f"/vagas-{slug}",
                        f"/empregos-{slug}",
                        f"/busca/{slug}",
                    ):
                        resp = client.get(f"{_BASE}{path}")
                        if resp.status_code >= 400:
                            continue
                        batch = _parse_html(resp.text, cap)
                        if batch:
                            break
                    if batch:
                        break
                _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Empregos.com.br falhou: %s", exc)
    return jobs[:max_jobs]
