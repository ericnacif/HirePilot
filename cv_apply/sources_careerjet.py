"""Fonte CareerJet — agregador (requer CAREERJET_API_KEY)."""

from __future__ import annotations

import logging
import os

import httpx

from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.sources import _active_queries, _append_unique, _fair_cap, _make_id, _strip_html

logger = logging.getLogger(__name__)

_API = "https://search.api.careerjet.net/v4/query"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _careerjet_key(settings) -> str:
    return (getattr(settings, "careerjet_api_key", None) or os.getenv("CAREERJET_API_KEY") or "").strip()


def search_careerjet(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    api_key = _careerjet_key(settings)
    if not api_key:
        logger.info("CareerJet ignorado — defina CAREERJET_API_KEY.")
        return []

    queries = _active_queries(filters)
    location = (filters.location or settings.search_location or "Brasil").strip()
    jobs: list[JobPosting] = []
    seen: set[str] = set()

    params_base = {
        "locale_code": "pt_BR",
        "location": location,
        "sort": "date",
        "page_size": "50",
        "user_ip": "127.0.0.1",
        "user_agent": _UA,
    }
    headers = {
        "Referer": "https://hirepilot.local/search",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            for i, query in enumerate(queries):
                if len(jobs) >= max_jobs:
                    break
                cap = _fair_cap(
                    max_jobs - len(jobs), len(queries) - i,
                    floor=5 if filters.broad_mode else 8,
                    broad=filters.broad_mode,
                )
                params = {**params_base, "keywords": query or filters.keywords or "emprego"}
                resp = client.get(_API, params=params, auth=(api_key, ""), headers=headers)
                if resp.status_code == 403:
                    logger.warning("CareerJet: chave inválida ou IP não autorizado no painel.")
                    return jobs
                resp.raise_for_status()
                batch: list[JobPosting] = []
                data = resp.json()
                if data.get("type") != "JOBS":
                    continue
                for item in data.get("jobs") or []:
                    title = (item.get("title") or "").strip()
                    link = (item.get("url") or "").strip()
                    if not title or not link:
                        continue
                    desc = _strip_html(item.get("description") or "")
                    site = (item.get("site") or "").strip()
                    if site:
                        desc = f"Origem: {site}\n\n{desc}"
                    batch.append(
                        JobPosting(
                            id=_make_id("careerjet", link),
                            title=title,
                            company=(item.get("company") or site or "Empresa não informada").strip(),
                            location=(item.get("locations") or location).strip(),
                            url=link,
                            description=desc[:5000],
                            easy_apply=False,
                            posted_at=item.get("date"),
                        )
                    )
                    if len(batch) >= cap:
                        break
                _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("CareerJet falhou: %s", exc)

    return jobs[:max_jobs]
