"""Fonte Trampos.co — API pública (trampos.co/api/oportunidades)."""

from __future__ import annotations

import logging

import httpx

from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.relevance import extract_query_terms, term_in_job_text
from cv_apply.sources import _active_queries, _append_unique, _fair_cap, _make_id

logger = logging.getLogger(__name__)

_API_URL = "https://trampos.co/api/oportunidades"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _item_to_job(item: dict) -> JobPosting | None:
    opp = item.get("opportunity") if "opportunity" in item else item
    if not opp:
        return None
    title = (opp.get("name") or "").strip()
    url = (opp.get("permalink") or "").strip()
    if not title or not url:
        return None
    company = (opp.get("company_name") or "Empresa não informada").strip()
    return JobPosting(
        id=_make_id("trampos", str(opp.get("id") or title)),
        title=title,
        company=company,
        location="Brasil",
        url=url,
        description=f"Vaga publicada no Trampos.co — {company}.",
        easy_apply=False,
        posted_at=opp.get("published_at"),
    )


def search_trampos(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    queries = _active_queries(filters)
    terms = extract_query_terms(filters.keywords)
    jobs: list[JobPosting] = []
    seen: set[str] = set()

    try:
        with httpx.Client(timeout=25, headers=_HEADERS, follow_redirects=True) as client:
            for i, query in enumerate(queries):
                if len(jobs) >= max_jobs:
                    break
                cap = _fair_cap(
                    max_jobs - len(jobs), len(queries) - i,
                    floor=4 if filters.broad_mode else 6,
                    broad=filters.broad_mode,
                )
                page = 1
                while len(jobs) < max_jobs and page <= 5:
                    params: dict[str, str | int] = {"page": page}
                    if query:
                        params["q"] = query
                    resp = client.get(_API_URL, params=params)
                    resp.raise_for_status()
                    rows = resp.json()
                    if not isinstance(rows, list) or not rows:
                        break
                    batch: list[JobPosting] = []
                    for row in rows:
                        job = _item_to_job(row)
                        if not job:
                            continue
                        if not filters.broad_mode and terms:
                            hay = f"{job.title} {job.company} {job.description}".lower()
                            if not any(term_in_job_text(term, hay) for term in terms):
                                continue
                        if not filters.matches_date(None):
                            pass
                        batch.append(job)
                        if len(batch) >= cap:
                            break
                    before = len(jobs)
                    _append_unique(jobs, batch, seen, max_jobs)
                    if len(jobs) >= max_jobs or len(jobs) == before:
                        break
                    page += 1
    except Exception as exc:
        logger.warning("Trampos falhou: %s", exc)

    return jobs
