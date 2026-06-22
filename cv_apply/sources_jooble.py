"""Fonte Jooble — agregador internacional (requer JOOBLE_API_KEY)."""

from __future__ import annotations

import logging
import os

import httpx

from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.sources import _active_queries, _append_unique, _fair_cap, _make_id, _strip_html

logger = logging.getLogger(__name__)

_API_BASE = "https://jooble.org/api"


def _jooble_key(settings) -> str:
    return (getattr(settings, "jooble_api_key", None) or os.getenv("JOOBLE_API_KEY") or "").strip()


def search_jooble(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    api_key = _jooble_key(settings)
    if not api_key:
        logger.info("Jooble ignorado — defina JOOBLE_API_KEY (grátis em jooble.org/api/about).")
        return []

    queries = _active_queries(filters)
    location = (filters.location or "Brasil").strip() or "Brasil"
    jobs: list[JobPosting] = []
    seen: set[str] = set()

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
                body = {
                    "keywords": query or filters.keywords or "emprego",
                    "location": location,
                    "page": "1",
                }
                resp = client.post(
                    f"{_API_BASE}/{api_key}",
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 403:
                    logger.warning("Jooble: chave de API inválida.")
                    return jobs
                resp.raise_for_status()
                batch: list[JobPosting] = []
                for item in resp.json().get("jobs") or []:
                    title = (item.get("title") or "").strip()
                    link = (item.get("link") or "").strip()
                    if not title or not link:
                        continue
                    desc = _strip_html(item.get("snippet") or "")
                    sal = (item.get("salary") or "").strip()
                    if sal:
                        desc = f"Salário: {sal}\n\n{desc}"
                    src = (item.get("source") or "").strip()
                    if src:
                        desc = f"Origem: {src}\n\n{desc}"
                    batch.append(
                        JobPosting(
                            id=_make_id("jooble", str(item.get("id") or link)),
                            title=title,
                            company=(item.get("company") or "Empresa não informada").strip(),
                            location=(item.get("location") or location).strip(),
                            url=link,
                            description=desc[:5000],
                            easy_apply=False,
                            posted_at=item.get("updated"),
                        )
                    )
                    if len(batch) >= cap:
                        break
                _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Jooble falhou: %s", exc)

    return jobs
