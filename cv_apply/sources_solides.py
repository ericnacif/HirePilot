"""Fonte Sólides Vagas — API pública do portal (vagas.solides.com.br)."""

from __future__ import annotations

import logging
import re

import httpx

from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.relevance import extract_query_terms, term_in_job_text
from cv_apply.sources import (
    _active_queries,
    _append_unique,
    _fair_cap,
    _make_id,
    _parse_date,
    _strip_html,
)

logger = logging.getLogger(__name__)

_API_URL = "https://apigw.solides.com.br/jobs/v3/portal-vacancies-new"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://vagas.solides.com.br",
    "Referer": "https://vagas.solides.com.br/",
}


def _slugify_title(title: str) -> str:
    text = (title or "").lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:80] or "vaga"


def _portal_url(job_id: int | str, title: str) -> str:
    return f"https://vagas.solides.com.br/vaga/{job_id}/{_slugify_title(title)}"


def _location_label(item: dict) -> str:
    city = (item.get("city") or {}).get("name") or ""
    state = (item.get("state") or {}).get("code") or ""
    loc = ", ".join(p for p in (city, state) if p)
    if item.get("homeOffice") or (item.get("jobType") or "").lower() == "remoto":
        return f"{loc} (Remoto)" if loc else "Remoto"
    return loc or "Brasil"


def _seniority_in_item(item: dict) -> str:
    parts = []
    for s in item.get("seniority") or []:
        if isinstance(s, dict):
            parts.append(s.get("name") or "")
        else:
            parts.append(str(s))
    return " ".join(parts)


def _item_to_job(item: dict) -> JobPosting:
    title = item.get("title") or "Sem título"
    job_id = item.get("id")
    desc = _strip_html(item.get("description") or "")
    seniority_txt = _seniority_in_item(item)
    if seniority_txt:
        desc = f"Nível: {seniority_txt}\n\n{desc}"
    url = item.get("redirectLink") or _portal_url(job_id, title)
    return JobPosting(
        id=_make_id("solides", str(job_id)),
        title=title,
        company=item.get("companyName") or "Empresa não informada",
        location=_location_label(item),
        url=url,
        description=desc[:8000],
        easy_apply=False,
        posted_at=item.get("createdAt"),
    )


def search_solides(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    queries = _active_queries(filters)
    terms = extract_query_terms(filters.keywords)
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
                page = 1
                batch: list[JobPosting] = []
                while len(batch) < cap and page <= 4:
                    params = {
                        "termo": query or filters.keywords or "tecnologia",
                        "title": "",
                        "locations": "",
                        "take": min(50, cap - len(batch) + 10),
                        "page": str(page),
                    }
                    resp = client.get(_API_URL, params=params)
                    resp.raise_for_status()
                    payload = resp.json()
                    items = (payload.get("data") or {}).get("data") or []
                    if not items:
                        break
                    for item in items:
                        job = _item_to_job(item)
                        published = _parse_date(job.posted_at)
                        if not filters.matches_date(published):
                            continue
                        if not filters.broad_mode and not filters.allows_remote():
                            loc = (job.location or "").lower()
                            if "remoto" in loc and filters.workplace and "remoto" not in filters.workplace:
                                continue
                        haystack = f"{job.title} {job.description}"
                        if terms and not any(term_in_job_text(t, haystack) for t in terms):
                            continue
                        batch.append(job)
                        if len(batch) >= cap:
                            break
                    page += 1
                _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Sólides falhou: %s", exc)

    return jobs[:max_jobs]
