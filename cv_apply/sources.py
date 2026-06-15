"""Fontes de vagas: LinkedIn, Gupy, InfoJobs, Remotive, RemoteOK.

Cada fonte retorna uma lista de JobPosting já filtrada pelos filtros do usuário.
APIs públicas (Remotive, RemoteOK, Gupy) não exigem login e têm baixo risco.
LinkedIn e InfoJobs usam navegador (Playwright).
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from cv_apply.config import Settings
from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting

logger = logging.getLogger(__name__)

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Plataformas que são exclusivamente remotas
REMOTE_ONLY_SOURCES = {"remotive", "remoteok"}


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_date(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except Exception:
            return None
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in (None,):
        try:
            return datetime.fromisoformat(text)
        except Exception:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value)[:19], fmt)
        except Exception:
            continue
    return None


def _make_id(source: str, native_id: str) -> str:
    raw = f"{source}:{native_id}"
    if len(raw) > 60:
        return f"{source}:" + hashlib.md5(native_id.encode()).hexdigest()[:16]
    return raw


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _dedupe_key(job: JobPosting) -> str:
    """Chave para identificar a mesma vaga em fontes diferentes.

    Remove acentos antes de tudo para que "Júnior"/"Sênior" sejam reconhecidos
    e descartados como sufixo de senioridade.
    """
    title = re.sub(r"[^a-z0-9]+", " ", _strip_accents(job.title.lower())).strip()
    company = re.sub(r"[^a-z0-9]+", " ", _strip_accents(job.company.lower())).strip()
    # remove sufixos de senioridade comuns para agrupar variações próximas
    title = re.sub(r"\b(jr|sr|pl|junior|senior|pleno|trainee|estagio)\b", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return f"{title}|{company}"


def dedupe_jobs(jobs: list[JobPosting]) -> list[JobPosting]:
    """Remove vagas duplicadas entre fontes, mantendo a mais completa.

    Em caso de empate, prioriza vagas com Easy Apply e descrição mais longa.
    """
    best: dict[str, JobPosting] = {}
    for job in jobs:
        key = _dedupe_key(job)
        current = best.get(key)
        if current is None:
            best[key] = job
            continue
        # escolhe a "melhor" versão da vaga duplicada
        current_score = (current.easy_apply, len(current.description or ""))
        new_score = (job.easy_apply, len(job.description or ""))
        if new_score > current_score:
            best[key] = job
    return list(best.values())


# --------------------------------------------------------------------------- #
# Remotive (https://remotive.com) — API pública, só vagas remotas
# --------------------------------------------------------------------------- #
def search_remotive(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    if not filters.allows_remote():
        logger.info("Remotive ignorado (filtro não inclui remoto).")
        return []

    url = "https://remotive.com/api/remote-jobs"
    params = {"search": filters.keywords, "limit": str(max_jobs)}
    jobs: list[JobPosting] = []
    try:
        with httpx.Client(timeout=30, headers=_HTTP_HEADERS, follow_redirects=True) as c:
            resp = c.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Remotive falhou: %s", exc)
        return []

    for item in data.get("jobs", [])[:max_jobs]:
        published = _parse_date(item.get("publication_date"))
        if not filters.matches_date(published):
            continue
        if not filters.matches_generic_job_type(item.get("job_type", "")):
            continue
        jobs.append(
            JobPosting(
                id=_make_id("remotive", str(item.get("id"))),
                title=item.get("title", "Sem título"),
                company=item.get("company_name", "Empresa não informada"),
                location=item.get("candidate_required_location") or "Remoto",
                url=item.get("url", ""),
                description=_strip_html(item.get("description", "")),
                easy_apply=False,
                posted_at=item.get("publication_date"),
            )
        )
    return jobs


# --------------------------------------------------------------------------- #
# RemoteOK (https://remoteok.com) — API pública, só vagas remotas
# --------------------------------------------------------------------------- #
def search_remoteok(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    if not filters.allows_remote():
        logger.info("RemoteOK ignorado (filtro não inclui remoto).")
        return []

    url = "https://remoteok.com/api"
    try:
        with httpx.Client(timeout=30, headers=_HTTP_HEADERS, follow_redirects=True) as c:
            resp = c.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("RemoteOK falhou: %s", exc)
        return []

    keywords = [k for k in filters.keywords.lower().split() if k]
    jobs: list[JobPosting] = []
    for item in data:
        if not isinstance(item, dict) or "position" not in item:
            continue  # primeiro item é aviso legal

        haystack = f"{item.get('position','')} {item.get('description','')} {' '.join(item.get('tags', []))}".lower()
        if keywords and not any(k in haystack for k in keywords):
            continue

        published = _parse_date(item.get("date") or item.get("epoch"))
        if not filters.matches_date(published):
            continue

        jobs.append(
            JobPosting(
                id=_make_id("remoteok", str(item.get("id") or item.get("slug"))),
                title=item.get("position", "Sem título"),
                company=item.get("company", "Empresa não informada"),
                location=item.get("location") or "Remoto",
                url=item.get("url") or item.get("apply_url", ""),
                description=_strip_html(item.get("description", "")),
                easy_apply=False,
                posted_at=str(item.get("date") or ""),
            )
        )
        if len(jobs) >= max_jobs:
            break
    return jobs


# --------------------------------------------------------------------------- #
# Gupy (https://portal.gupy.io) — API pública do portal de empregabilidade
# --------------------------------------------------------------------------- #
def search_gupy(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    url = "https://employability-portal.gupy.io/api/v1/jobs"
    headers = {
        **_HTTP_HEADERS,
        "Origin": "https://portal.gupy.io",
        "Referer": "https://portal.gupy.io/",
    }
    jobs: list[JobPosting] = []
    offset = 0
    page_size = min(max_jobs, 100)
    wp_types = filters.gupy_workplace_types()
    job_types = filters.gupy_job_types()

    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as c:
            while len(jobs) < max_jobs:
                params = {
                    "jobName": filters.keywords,
                    "limit": str(page_size),
                    "offset": str(offset),
                }
                if filters.only_remote():
                    params["isRemoteWork"] = "true"
                resp = c.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", [])
                if not items:
                    break

                for item in items:
                    wp = (item.get("workplaceType") or "").lower()
                    if wp_types and wp not in wp_types:
                        continue
                    if job_types and item.get("type") not in job_types:
                        continue
                    published = _parse_date(item.get("publishedDate"))
                    if not filters.matches_date(published):
                        continue

                    city = item.get("city") or ""
                    state = item.get("state") or ""
                    loc = ", ".join(p for p in (city, state) if p) or item.get("country", "")
                    if item.get("isRemoteWork"):
                        loc = f"{loc} (Remoto)" if loc else "Remoto"

                    jobs.append(
                        JobPosting(
                            id=_make_id("gupy", str(item.get("id"))),
                            title=item.get("name", "Sem título"),
                            company=item.get("careerPageName", "Empresa não informada"),
                            location=loc,
                            url=item.get("jobUrl", ""),
                            description=_strip_html(item.get("description", "")),
                            easy_apply=False,
                            posted_at=item.get("publishedDate"),
                        )
                    )
                    if len(jobs) >= max_jobs:
                        break

                pagination = data.get("pagination", {})
                total = pagination.get("total", 0)
                offset += page_size
                if offset >= total:
                    break
    except Exception as exc:
        logger.warning("Gupy falhou: %s", exc)

    return jobs


# --------------------------------------------------------------------------- #
# InfoJobs (https://www.infojobs.com.br) — scraping da busca (Playwright)
# --------------------------------------------------------------------------- #
def _slugify_keywords(keywords: str) -> str:
    text = keywords.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text or "desenvolvedor"


def search_infojobs(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    from playwright.sync_api import sync_playwright

    slug = _slugify_keywords(filters.keywords)
    base = "https://www.infojobs.com.br"
    url = f"{base}/vagas-de-emprego-{slug}.aspx"
    jobs: list[JobPosting] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.headless)
            page = browser.new_page(locale="pt-BR")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)

            cards = page.locator("div.js_rowCard")
            count = min(cards.count(), max_jobs)
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

                    full_url = href if href.startswith("http") else f"{base}{href}"
                    jobs.append(
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
                except Exception as exc:
                    logger.debug("InfoJobs card %d erro: %s", i, exc)

            browser.close()
    except Exception as exc:
        logger.warning("InfoJobs falhou: %s", exc)

    return jobs


# --------------------------------------------------------------------------- #
# LinkedIn — usa o cliente Playwright existente (login assistido)
# --------------------------------------------------------------------------- #
def search_linkedin(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    from cv_apply.linkedin import LinkedInClient

    with LinkedInClient(settings) as client:
        return client.search_jobs(max_jobs=max_jobs)


SOURCE_FUNCS: dict[str, Callable[[Settings, SearchFilters, int], list[JobPosting]]] = {
    "linkedin": search_linkedin,
    "gupy": search_gupy,
    "infojobs": search_infojobs,
    "remotive": search_remotive,
    "remoteok": search_remoteok,
}

AVAILABLE_SOURCES = list(SOURCE_FUNCS.keys())

# Fontes que sobem um navegador (Playwright). Não podem rodar em paralelo entre
# si — a API síncrona do Playwright não é thread-safe e o LinkedIn pede login
# interativo. Rodam em sequência; as demais (APIs HTTP) rodam em paralelo.
BROWSER_SOURCES = {"linkedin", "infojobs"}


def run_sources(
    settings: Settings,
    max_jobs: int,
    on_log: Optional[Callable[[str], None]] = None,
) -> dict[str, list[JobPosting]]:
    """Executa as fontes habilitadas e retorna {fonte: [vagas]}.

    Fontes de API rodam em paralelo (mais rápido); fontes que usam navegador
    rodam em sequência.
    """
    filters = SearchFilters.from_settings(settings)
    results: dict[str, list[JobPosting]] = {}

    def log(msg: str) -> None:
        if on_log:
            on_log(msg)
        logger.info(msg)

    requested = []
    for name in settings.search_sources:
        if name not in SOURCE_FUNCS:
            log(f"Fonte desconhecida ignorada: {name}")
            continue
        requested.append(name)

    api_sources = [n for n in requested if n not in BROWSER_SOURCES]
    browser_sources = [n for n in requested if n in BROWSER_SOURCES]

    def run_one(name: str) -> tuple[str, list[JobPosting]]:
        try:
            found = SOURCE_FUNCS[name](settings, filters, max_jobs)
            return name, found
        except Exception as exc:
            log(f"  {name}: erro ({exc})")
            return name, []

    if api_sources:
        log(f"Buscando em paralelo: {', '.join(api_sources)}...")
        with ThreadPoolExecutor(max_workers=len(api_sources)) as pool:
            futures = {pool.submit(run_one, name): name for name in api_sources}
            for future in as_completed(futures):
                name, found = future.result()
                results[name] = found
                log(f"  {name}: {len(found)} vaga(s)")

    for name in browser_sources:
        log(f"Buscando em '{name}'...")
        _, found = run_one(name)
        results[name] = found
        log(f"  {name}: {len(found)} vaga(s)")

    return results
