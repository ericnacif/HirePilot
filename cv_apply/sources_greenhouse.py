"""Fonte Greenhouse — boards públicos de empresas tech (API JSON)."""

from __future__ import annotations

import logging

import httpx

from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.relevance import extract_query_terms, term_in_job_text
from cv_apply.sources import (
    _active_queries,
    _append_unique,
    _fair_cap,
    _make_id,
    _strip_html,
)

logger = logging.getLogger(__name__)

_HTTP_HEADERS = {
    "User-Agent": "HirePilot/1.0 (+https://github.com/ericnacif/vagamatch)",
    "Accept": "application/json",
}

# Boards públicos conhecidos (tech / remoto-friendly)
GREENHOUSE_BOARDS = (
    "gitlab", "hashicorp", "datadog", "cloudflare", "mongodb",
    "elastic", "okta", "dropbox", "asana", "figma", "notion",
    "airbnb", "stripe", "shopify", "hubspot", "twilio", "zendesk",
    "coinbase", "robinhood", "discord", "reddit", "lyft", "doordash",
)


def search_greenhouse(
    settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    queries = _active_queries(filters)
    if filters.broad_mode and not (filters.keywords or "").strip() and not queries[0]:
        terms: list[str] = []
    else:
        terms = extract_query_terms(filters.keywords)
        if not terms and queries:
            terms = [q for q in queries if q]

    jobs: list[JobPosting] = []
    seen: set[str] = set()
    per_board = max(3, max_jobs // max(len(GREENHOUSE_BOARDS), 1))

    try:
        with httpx.Client(timeout=20, headers=_HTTP_HEADERS, follow_redirects=True) as client:
            for board in GREENHOUSE_BOARDS:
                if len(jobs) >= max_jobs:
                    break
                url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
                try:
                    resp = client.get(url, params={"content": "true"})
                    if resp.status_code != 200:
                        continue
                    items = resp.json().get("jobs", [])
                except Exception:
                    continue

                batch: list[JobPosting] = []
                for item in items:
                    title = item.get("title", "")
                    company = board.replace("-", " ").title()
                    loc = ""
                    locs = item.get("location") or {}
                    if isinstance(locs, dict):
                        loc = locs.get("name", "")
                    elif isinstance(locs, str):
                        loc = locs
                    desc = _strip_html(item.get("content", "") or "")
                    haystack = f"{title} {desc} {loc}"
                    if terms and not any(term_in_job_text(t, haystack) for t in terms):
                        continue
                    if not filters.matches_date(None):
                        pass  # greenhouse não traz data confiável no list
                    batch.append(
                        JobPosting(
                            id=_make_id("greenhouse", f"{board}:{item.get('id')}"),
                            title=title or "Sem título",
                            company=company,
                            location=loc or "Remoto",
                            url=item.get("absolute_url", ""),
                            description=desc[:8000],
                            easy_apply=False,
                        )
                    )
                    if len(batch) >= per_board:
                        break
                _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Greenhouse falhou: %s", exc)

    return jobs[:max_jobs]
