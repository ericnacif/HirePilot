"""Fonte Indeed Brasil — RSS público com filtro de data."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote_plus

import httpx

from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.sources import _active_queries, _append_unique, _fair_cap, _make_id, _strip_html

logger = logging.getLogger(__name__)

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_FROMAGE = {"24h": "1", "semana": "7", "mes": "30"}


def _parse_pub_date(value: str | None):
    if not value:
        return None
    try:
        return parsedate_to_datetime(value.strip())
    except (TypeError, ValueError):
        return None


def _parse_rss_item(item: ET.Element) -> JobPosting | None:
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    if not title or not link:
        return None
    raw_desc = item.findtext("description") or ""
    desc = _strip_html(unescape(raw_desc))
    company = ""
    location = ""
    m_co = re.search(r"<b>Empresa:</b>\s*([^<]+)", raw_desc, re.I)
    m_loc = re.search(r"<b>Local:</b>\s*([^<]+)", raw_desc, re.I)
    if m_co:
        company = m_co.group(1).strip()
    if m_loc:
        location = m_loc.group(1).strip()
    pub = item.findtext("pubDate")
    native_id = link.rstrip("/").split("/")[-1] or title
    return JobPosting(
        id=_make_id("indeed", native_id),
        title=title,
        company=company or "Empresa não informada",
        location=location or "Brasil",
        url=link,
        description=desc[:5000],
        easy_apply=False,
        posted_at=pub,
    )


def search_indeed(settings, filters: SearchFilters, max_jobs: int) -> list[JobPosting]:
    queries = _active_queries(filters)
    location = (filters.location or "Brasil").strip()
    fromage = _FROMAGE.get(filters.date_posted, "")
    jobs: list[JobPosting] = []
    seen: set[str] = set()

    try:
        with httpx.Client(timeout=25, headers=_HTTP_HEADERS, follow_redirects=True) as client:
            for i, query in enumerate(queries):
                if len(jobs) >= max_jobs:
                    break
                cap = _fair_cap(
                    max_jobs - len(jobs), len(queries) - i,
                    floor=5 if filters.broad_mode else 8,
                    broad=filters.broad_mode,
                )
                q = quote_plus(query or filters.keywords or "desenvolvedor")
                loc = quote_plus(location)
                extra = f"&fromage={fromage}" if fromage else ""
                urls = [
                    f"https://br.indeed.com/rss?q={q}&l={loc}{extra}",
                    f"https://rss.indeed.com/rss?q={q}&l={loc}{extra}",
                ]
                batch: list[JobPosting] = []
                for url in urls:
                    if batch:
                        break
                    try:
                        resp = client.get(url)
                        if resp.status_code != 200:
                            continue
                        root = ET.fromstring(resp.text)
                    except Exception as exc:
                        logger.debug("Indeed RSS '%s': %s", query, exc)
                        continue
                    for item in root.findall(".//item"):
                        job = _parse_rss_item(item)
                        if not job:
                            continue
                        published = _parse_pub_date(job.posted_at)
                        if not filters.matches_date(published):
                            continue
                        batch.append(job)
                        if len(batch) >= cap:
                            break
                _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Indeed falhou: %s", exc)

    return jobs[:max_jobs]
