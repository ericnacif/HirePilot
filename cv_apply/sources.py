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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

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
# Plataformas que são exclusivamente remotas
REMOTE_ONLY_SOURCES = {"remotive", "remoteok"}


def source_zero_hint(name: str, filters: SearchFilters) -> str | None:
    """Explica por que uma fonte pode ter voltado 0 vagas."""
    if name in REMOTE_ONLY_SOURCES and not filters.allows_remote():
        return "marque «remoto» nos filtros de local"
    if name == "indeed":
        return "RSS do Indeed pode estar bloqueado — tente Gupy ou InfoJobs"
    if name == "remoteok":
        return "nenhuma vaga remota bateu com os termos ou data"
    if name == "infojobs":
        return "requer navegador — marque a fonte e aguarde o scraping"
    if name == "linkedin":
        return "requer login no navegador na primeira vez"
    if name == "greenhouse":
        return "boards US fixos — poucas vagas BR"
    return None


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except Exception:
            return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
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


def _normalize_url(url: str) -> str:
    """URL canônica para deduplicar a mesma vaga em fontes diferentes."""
    u = (url or "").lower().strip()
    u = re.sub(r"[?#].*$", "", u)
    u = u.rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u


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

    Primeiro unifica por URL; depois por título+empresa normalizados.
    """
    by_url: dict[str, JobPosting] = {}
    no_url: list[JobPosting] = []
    for job in jobs:
        key = _normalize_url(job.url)
        if not key:
            no_url.append(job)
            continue
        current = by_url.get(key)
        if current is None or _job_quality(job) > _job_quality(current):
            by_url[key] = job

    merged = list(by_url.values()) + no_url

    best: dict[str, JobPosting] = {}
    for job in merged:
        key = _dedupe_key(job)
        current = best.get(key)
        if current is None or _job_quality(job) > _job_quality(current):
            best[key] = job
    return list(best.values())


def _job_quality(job: JobPosting) -> tuple:
    return (job.easy_apply, len(job.description or ""), len(job.url or ""))


def _fair_cap(
    remaining: int, queries_left: int, *, floor: int = 8, broad: bool = False
) -> int:
    """Quota justa por termo de busca para diversificar resultados entre queries."""
    if remaining <= 0 or queries_left <= 0:
        return 0
    if queries_left == 1:
        return remaining
    per = max(1, remaining // queries_left)
    if broad:
        return min(remaining, per)
    return min(remaining, max(min(floor, remaining), per))


_BROAD_MAX_QUERIES = 6


def _active_queries(filters: SearchFilters) -> list[str]:
    """Termos de busca ativos (setor multi-query ou palavra-chave do usuário)."""
    queries = [q.strip() for q in (filters.search_queries or []) if q.strip()]
    if not queries:
        kw = (filters.keywords or "").strip()
        if kw:
            queries = _keyword_candidates(kw)
        else:
            queries = [""]
    if filters.broad_mode and len(queries) > _BROAD_MAX_QUERIES:
        return queries[:_BROAD_MAX_QUERIES]
    return queries


def _append_unique(
    target: list[JobPosting], batch: list[JobPosting], seen: set[str], limit: int
) -> None:
    for job in batch:
        if len(target) >= limit:
            return
        if job.id not in seen:
            seen.add(job.id)
            target.append(job)


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
    queries = _active_queries(filters)
    jobs: list[JobPosting] = []
    seen: set[str] = set()

    try:
        with httpx.Client(timeout=30, headers=_HTTP_HEADERS, follow_redirects=True) as c:
            for i, query in enumerate(queries):
                if len(jobs) >= max_jobs:
                    break
                cap = _fair_cap(
                    max_jobs - len(jobs), len(queries) - i,
                    floor=5 if filters.broad_mode else 8,
                    broad=filters.broad_mode,
                )
                params = {"search": query, "limit": str(max(cap, 1))}
                resp = c.get(url, params=params)
                resp.raise_for_status()
                batch: list[JobPosting] = []
                for item in resp.json().get("jobs", []):
                    published = _parse_date(item.get("publication_date"))
                    if not filters.matches_date(published):
                        continue
                    if not filters.broad_mode and not filters.matches_generic_job_type(
                        item.get("job_type", "")
                    ):
                        continue
                    sal = item.get("salary") or ""
                    desc = _strip_html(item.get("description", ""))
                    if sal:
                        desc = f"Salário: {sal}\n\n{desc}"
                    batch.append(
                        JobPosting(
                            id=_make_id("remotive", str(item.get("id"))),
                            title=item.get("title", "Sem título"),
                            company=item.get("company_name", "Empresa não informada"),
                            location=item.get("candidate_required_location") or "Remoto",
                            url=item.get("url", ""),
                            description=desc,
                            easy_apply=False,
                            posted_at=item.get("publication_date"),
                        )
                    )
                _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Remotive falhou: %s", exc)

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

    from cv_apply.relevance import extract_query_terms, term_in_job_text

    url = "https://remoteok.com/api"
    headers = {**_HTTP_HEADERS, "Accept": "application/json"}
    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as c:
            resp = c.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("RemoteOK falhou: %s", exc)
        return []

    if filters.broad_mode and not (filters.keywords or "").strip():
        terms: list[str] = []
    else:
        terms = extract_query_terms(filters.keywords)
        if not terms and (filters.keywords or "").strip():
            terms = [t for t in filters.keywords.lower().split() if len(t) > 1]

    def _collect(require_terms: bool) -> list[tuple[datetime | None, dict]]:
        rows: list[tuple[datetime | None, dict]] = []
        for item in data:
            if not isinstance(item, dict) or "position" not in item:
                continue
            haystack = (
                f"{item.get('position', '')} {item.get('description', '')} "
                f"{' '.join(item.get('tags', []))}"
            )
            if require_terms and terms and not any(term_in_job_text(t, haystack) for t in terms):
                continue
            published = _parse_date(item.get("date") or item.get("epoch"))
            if not filters.matches_date(published):
                continue
            rows.append((published, item))
        rows.sort(
            key=lambda row: row[0] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return rows

    rows = _collect(require_terms=True)
    if not rows and filters.broad_mode and terms:
        rows = _collect(require_terms=False)
        if rows:
            logger.info("RemoteOK: ampliando busca (sem filtro de termos)")

    jobs: list[JobPosting] = []
    for _published, item in rows:
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
def _keyword_candidates(keywords: str) -> list[str]:
    """Algumas fontes (Gupy, InfoJobs) casam as palavras-chave de forma quase
    literal, então frases longas (ex.: vindas de um setor) zeram os resultados.
    Geramos candidatos do mais específico ao mais genérico: frase completa →
    2 primeiras palavras → primeira palavra (geralmente o cargo)."""
    kw = (keywords or "").strip()
    if not kw:
        return [""]
    words = kw.split()
    candidates = [kw]
    if len(words) > 2:
        candidates.append(" ".join(words[:2]))
    if len(words) > 1:
        candidates.append(words[0])
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


# Alias retrocompatível
_gupy_keyword_candidates = _keyword_candidates


def search_gupy(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    url = "https://employability-portal.gupy.io/api/v1/jobs"
    headers = {
        **_HTTP_HEADERS,
        "Origin": "https://portal.gupy.io",
        "Referer": "https://portal.gupy.io/",
    }
    wp_types = [] if filters.broad_mode else filters.gupy_workplace_types()
    job_types = [] if filters.broad_mode else filters.gupy_job_types()

    def _fetch(client: httpx.Client, job_name: str, cap: int) -> list[JobPosting]:
        found: list[JobPosting] = []
        offset = 0
        page_size = min(max(cap, 1), 100)
        while len(found) < cap:
            params = {
                "jobName": job_name,
                "limit": str(page_size),
                "offset": str(offset),
            }
            resp = client.get(url, params=params)
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

                found.append(
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
                if len(found) >= cap:
                    break

            pagination = data.get("pagination", {})
            total = pagination.get("total", 0)
            offset += page_size
            if offset >= total:
                break
        return found

    queries = _active_queries(filters)
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as c:
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
                    batch = _fetch(c, candidate, cap)
                    if batch:
                        if candidate != query:
                            logger.info("Gupy: '%s' sem resultados; usando '%s'", query, candidate)
                        break
                _append_unique(jobs, batch, seen, max_jobs)
    except Exception as exc:
        logger.warning("Gupy falhou: %s", exc)

    return jobs[:max_jobs]


# --------------------------------------------------------------------------- #
# InfoJobs (https://www.infojobs.com.br) — scraping da busca (Playwright)
# --------------------------------------------------------------------------- #
def _slugify_keywords(keywords: str) -> str:
    text = keywords.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text or "desenvolvedor"


def _infojobs_description(page, url: str) -> str:
    """Busca descrição na página da vaga (best-effort)."""
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


def search_infojobs(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    from playwright.sync_api import sync_playwright

    base = "https://www.infojobs.com.br"

    def _scrape(page, keywords: str, cap: int) -> list[JobPosting]:
        slug = _slugify_keywords(keywords)
        page.goto(
            f"{base}/vagas-de-emprego-{slug}.aspx",
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

                full_url = href if href.startswith("http") else f"{base}{href}"
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

    jobs: list[JobPosting] = []
    seen: set[str] = set()
    queries = _active_queries(filters)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.headless)
            page = browser.new_page(locale="pt-BR")
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
                        if candidate != query:
                            logger.info(
                                "InfoJobs: '%s' sem resultados; usando '%s'",
                                query, candidate,
                            )
                        break
                _append_unique(jobs, batch, seen, max_jobs)
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

    try:
        with LinkedInClient(settings) as client:
            return client.search_jobs(
                max_jobs=max_jobs,
                fetch_descriptions=max_jobs <= 20,
            )
    except Exception as exc:
        logger.warning("LinkedIn falhou: %s", exc)
        return []


def search_greenhouse(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    from cv_apply.sources_greenhouse import search_greenhouse as _search

    return _search(settings, filters, max_jobs)


def search_indeed(
    settings: Settings, filters: SearchFilters, max_jobs: int
) -> list[JobPosting]:
    from cv_apply.sources_indeed import search_indeed as _search

    return _search(settings, filters, max_jobs)


SOURCE_FUNCS: dict[str, Callable[[Settings, SearchFilters, int], list[JobPosting]]] = {
    "linkedin": search_linkedin,
    "gupy": search_gupy,
    "infojobs": search_infojobs,
    "remotive": search_remotive,
    "remoteok": search_remoteok,
    "greenhouse": search_greenhouse,
    "indeed": search_indeed,
}

AVAILABLE_SOURCES = list(SOURCE_FUNCS.keys())


def register_source(
    name: str,
    searcher: Callable[[Settings, SearchFilters, int], list[JobPosting]],
) -> None:
    """Registra uma fonte adicional sem alterar o pipeline de busca."""
    key = re.sub(r"[^a-z0-9_-]", "", (name or "").lower())[:40]
    if not key or not callable(searcher):
        raise ValueError("Fonte inválida.")
    SOURCE_FUNCS[key] = searcher
    if key not in AVAILABLE_SOURCES:
        AVAILABLE_SOURCES.append(key)

# Fontes que sobem um navegador (Playwright). Não podem rodar em paralelo entre
# si — a API síncrona do Playwright não é thread-safe e o LinkedIn pede login
# interativo. Rodam em sequência; as demais (APIs HTTP) rodam em paralelo.
BROWSER_SOURCES = {"linkedin", "infojobs"}


def run_sources(
    settings: Settings,
    max_jobs: int,
    on_log: Callable[[str], None] | None = None,
    on_source_done: Callable[[str, list[JobPosting]], None] | None = None,
    use_cache: bool = True,
) -> tuple[dict[str, list[JobPosting]], dict[str, dict]]:
    """Executa as fontes habilitadas. Retorna (vagas, meta por fonte)."""
    from cv_apply.search_cache import get_search_cache

    filters = SearchFilters.from_settings(settings)
    cache = get_search_cache() if use_cache else None
    results: dict[str, list[JobPosting]] = {}
    source_meta: dict[str, dict] = {}

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
        cache_key = cache.make_key(name, settings, filters, max_jobs) if cache else ""
        if cache:
            hit = cache.get(cache_key)
            if hit is not None:
                log(f"  {name}: {len(hit)} vaga(s) (cache)")
                source_meta[name] = {"cached": True}
                if on_source_done:
                    on_source_done(name, hit)
                return name, hit
        try:
            found = SOURCE_FUNCS[name](settings, filters, max_jobs)
            if cache:
                cache.set(cache_key, found)
            hint = source_zero_hint(name, filters) if not found else None
            source_meta[name] = {"cached": False, "hint": hint}
            return name, found
        except Exception as exc:
            log(f"  {name}: erro ({exc})")
            source_meta[name] = {"cached": False, "hint": str(exc)[:120]}
            return name, []

    if api_sources:
        log(f"Buscando em paralelo: {', '.join(api_sources)}...")
        with ThreadPoolExecutor(max_workers=len(api_sources)) as pool:
            futures = {pool.submit(run_one, name): name for name in api_sources}
            for future in as_completed(futures):
                name, found = future.result()
                results[name] = found
                log(f"  {name}: {len(found)} vaga(s)")
                if on_source_done:
                    on_source_done(name, found)

    for name in browser_sources:
        log(f"Buscando em '{name}'...")
        name, found = run_one(name)
        results[name] = found
        log(f"  {name}: {len(found)} vaga(s)")
        if on_source_done:
            on_source_done(name, found)

    return results, source_meta
