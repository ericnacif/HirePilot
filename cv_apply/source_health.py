"""Health check proativo das fontes de vagas (ping leve + estado do navegador)."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Literal

import httpx

from cv_apply.config import Settings, get_settings
from cv_apply.sources import _HTTP_HEADERS, AVAILABLE_SOURCES

logger = logging.getLogger(__name__)

SourceStatus = Literal["ok", "degraded", "down", "needs_login", "browser", "unavailable"]

_HEALTH_CACHE: dict[str, Any] = {"at": 0.0, "sources": []}
_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 120
_HEALTH_TIMEOUT = 12.0

_SOURCE_LABELS = {
    "gupy": "Gupy",
    "indeed": "Indeed",
    "greenhouse": "Greenhouse",
    "remotive": "Remotive",
    "remoteok": "RemoteOK",
    "infojobs": "InfoJobs",
    "linkedin": "LinkedIn",
    "solides": "Sólides",
    "trampos": "Trampos.co",
    "jooble": "Jooble",
    "catho": "Catho",
    "vagascom": "Vagas.com",
    "careerjet": "CareerJet",
    "trabalhabrasil": "Trabalha Brasil",
    "empregoscom": "Empregos.com.br",
}


def _entry(
    source: str,
    status: SourceStatus,
    message: str,
    *,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "label": _SOURCE_LABELS.get(source, source),
        "status": status,
        "message": message,
        "latency_ms": latency_ms,
    }


def _playwright_ready() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "Playwright não instalado (edição leve ou Docker)"

    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            if exe:
                return True, ""
    except Exception as exc:
        return False, str(exc)[:120]
    return False, "Chromium não instalado — rode: playwright install chromium"


def _timed_get(url: str, *, headers: dict | None = None, params: dict | None = None) -> tuple[int, int]:
    t0 = time.perf_counter()
    with httpx.Client(
        timeout=_HEALTH_TIMEOUT,
        headers=headers or _HTTP_HEADERS,
        follow_redirects=True,
    ) as client:
        resp = client.get(url, params=params)
    latency = int((time.perf_counter() - t0) * 1000)
    return resp.status_code, latency


def check_gupy_health() -> dict[str, Any]:
    try:
        headers = {
            **_HTTP_HEADERS,
            "Origin": "https://portal.gupy.io",
            "Referer": "https://portal.gupy.io/",
        }
        code, latency = _timed_get(
            "https://employability-portal.gupy.io/api/v1/jobs",
            headers=headers,
            params={"jobName": "desenvolvedor", "limit": "1", "offset": "0"},
        )
        if code == 200:
            return _entry("gupy", "ok", "API respondendo normalmente", latency_ms=latency)
        if code in {403, 429}:
            return _entry("gupy", "degraded", f"API retornou HTTP {code}", latency_ms=latency)
        return _entry("gupy", "down", f"API retornou HTTP {code}", latency_ms=latency)
    except Exception as exc:
        return _entry("gupy", "down", str(exc)[:120])


def check_remotive_health() -> dict[str, Any]:
    try:
        code, latency = _timed_get(
            "https://remotive.com/api/remote-jobs",
            params={"limit": "1"},
        )
        if code == 200:
            return _entry("remotive", "ok", "API respondendo normalmente", latency_ms=latency)
        return _entry("remotive", "degraded", f"API retornou HTTP {code}", latency_ms=latency)
    except Exception as exc:
        return _entry("remotive", "down", str(exc)[:120])


def check_remoteok_health() -> dict[str, Any]:
    headers = {**_HTTP_HEADERS, "Accept": "application/json"}
    try:
        code, latency = _timed_get("https://remoteok.com/api", headers=headers)
        if code == 200:
            return _entry("remoteok", "ok", "API respondendo normalmente", latency_ms=latency)
        return _entry("remoteok", "degraded", f"API retornou HTTP {code}", latency_ms=latency)
    except Exception as exc:
        return _entry("remoteok", "down", str(exc)[:120])


def check_indeed_health() -> dict[str, Any]:
    headers = {
        **_HTTP_HEADERS,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    url = "https://br.indeed.com/rss?q=desenvolvedor&l=Brasil"
    try:
        code, latency = _timed_get(url, headers=headers)
        if code == 200:
            return _entry("indeed", "ok", "RSS respondendo normalmente", latency_ms=latency)
        if code in {403, 429, 503}:
            return _entry(
                "indeed",
                "degraded",
                f"RSS bloqueado ou instável (HTTP {code}) — tente Gupy",
                latency_ms=latency,
            )
        return _entry("indeed", "down", f"RSS retornou HTTP {code}", latency_ms=latency)
    except Exception as exc:
        return _entry("indeed", "down", str(exc)[:120])


def check_solides_health() -> dict[str, Any]:
    headers = {
        **_HTTP_HEADERS,
        "Accept": "application/json",
        "Origin": "https://vagas.solides.com.br",
        "Referer": "https://vagas.solides.com.br/",
    }
    try:
        code, latency = _timed_get(
            "https://apigw.solides.com.br/jobs/v3/portal-vacancies-new",
            headers=headers,
            params={"termo": "desenvolvedor", "take": "1", "page": "1"},
        )
        if code == 200:
            return _entry("solides", "ok", "API respondendo normalmente", latency_ms=latency)
        if code in {403, 429}:
            return _entry("solides", "degraded", f"API retornou HTTP {code}", latency_ms=latency)
        return _entry("solides", "down", f"API retornou HTTP {code}", latency_ms=latency)
    except Exception as exc:
        return _entry("solides", "down", str(exc)[:120])


def check_trampos_health() -> dict[str, Any]:
    try:
        code, latency = _timed_get(
            "https://trampos.co/api/oportunidades",
            params={"q": "desenvolvedor", "page": "1"},
        )
        if code == 200:
            return _entry("trampos", "ok", "API respondendo normalmente", latency_ms=latency)
        return _entry("trampos", "degraded", f"API retornou HTTP {code}", latency_ms=latency)
    except Exception as exc:
        return _entry("trampos", "down", str(exc)[:120])


def check_jooble_health(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    key = (getattr(settings, "jooble_api_key", None) or "").strip()
    if not key:
        import os
        key = (os.getenv("JOOBLE_API_KEY") or "").strip()
    if not key:
        return _entry(
            "jooble",
            "unavailable",
            "Defina JOOBLE_API_KEY — cadastro grátis em jooble.org/api/about",
        )
    try:
        t0 = time.perf_counter()
        with httpx.Client(timeout=_HEALTH_TIMEOUT) as client:
            resp = client.post(
                f"https://jooble.org/api/{key}",
                json={"keywords": "desenvolvedor", "location": "Brasil", "page": "1"},
            )
        latency = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            return _entry("jooble", "ok", "Agregador respondendo", latency_ms=latency)
        if resp.status_code == 403:
            return _entry("jooble", "down", "Chave de API inválida", latency_ms=latency)
        return _entry("jooble", "degraded", f"HTTP {resp.status_code}", latency_ms=latency)
    except Exception as exc:
        return _entry("jooble", "down", str(exc)[:120])


def check_greenhouse_health() -> dict[str, Any]:
    headers = {
        "User-Agent": "HirePilot/1.0 (+https://github.com/ericnacif/HirePilot)",
        "Accept": "application/json",
    }
    try:
        code, latency = _timed_get(
            "https://boards-api.greenhouse.io/v1/boards/gitlab/jobs",
            headers=headers,
        )
        if code == 200:
            return _entry("greenhouse", "ok", "API respondendo (boards US)", latency_ms=latency)
        return _entry("greenhouse", "degraded", f"API retornou HTTP {code}", latency_ms=latency)
    except Exception as exc:
        return _entry("greenhouse", "down", str(exc)[:120])


def check_infojobs_health() -> dict[str, Any]:
    ready, msg = _playwright_ready()
    if not ready:
        return _entry("infojobs", "unavailable", msg)
    try:
        code, latency = _timed_get("https://www.infojobs.com.br/")
        if code >= 500:
            return _entry("infojobs", "down", f"Site retornou HTTP {code}", latency_ms=latency)
        return _entry(
            "infojobs",
            "browser",
            "Disponível via navegador (scraping na busca)",
            latency_ms=latency,
        )
    except Exception as exc:
        return _entry("infojobs", "browser", f"Navegador OK — site: {str(exc)[:80]}")


def check_catho_health() -> dict[str, Any]:
    ready, msg = _playwright_ready()
    if not ready:
        return _entry("catho", "unavailable", msg)
    try:
        code, latency = _timed_get("https://www.catho.com.br/")
        if code >= 500:
            return _entry("catho", "down", f"Site retornou HTTP {code}", latency_ms=latency)
        return _entry(
            "catho",
            "browser",
            "Disponível via navegador visível (anti-bot Akamai)",
            latency_ms=latency,
        )
    except Exception as exc:
        return _entry("catho", "browser", f"Navegador OK — site: {str(exc)[:80]}")


def check_vagascom_health(settings: Settings) -> dict[str, Any]:
    ready, msg = _playwright_ready()
    if not ready:
        return _entry("vagascom", "unavailable", msg)

    try:
        from playwright.sync_api import sync_playwright

        from cv_apply.browser_portal import portal_data_dir

        settings.browser_data_dir.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(portal_data_dir(settings, "vagascom")),
                headless=True,
                viewport={"width": 900, "height": 700},
                locale="pt-BR",
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(
                "https://www.vagas.com.br/login-candidatos",
                wait_until="domcontentloaded",
                timeout=int(_HEALTH_TIMEOUT * 1000),
            )
            logged = "login-candidatos" not in page.url.lower() and not page.locator('input[name="login_candidatos_form[usuario]"]').count()
            if not logged:
                page.goto("https://www.vagas.com.br/vagas-de-emprego/desenvolvedor", wait_until="domcontentloaded", timeout=int(_HEALTH_TIMEOUT * 1000))
                logged = page.locator('a[href*="/vaga/"]').count() > 0
            ctx.close()
        latency = int((time.perf_counter() - t0) * 1000)
        if logged:
            return _entry("vagascom", "ok", "Sessão ativa", latency_ms=latency)
        return _entry(
            "vagascom",
            "needs_login",
            "Faça login manual na 1ª busca",
            latency_ms=latency,
        )
    except Exception as exc:
        return _entry("vagascom", "down", str(exc)[:120])


def check_careerjet_health(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    key = (getattr(settings, "careerjet_api_key", None) or "").strip()
    if not key:
        import os
        key = (os.getenv("CAREERJET_API_KEY") or "").strip()
    if not key:
        return _entry(
            "careerjet",
            "unavailable",
            "Defina CAREERJET_API_KEY — cadastro em careerjet.com.br/partners",
        )
    try:
        t0 = time.perf_counter()
        with httpx.Client(timeout=_HEALTH_TIMEOUT) as client:
            resp = client.get(
                "https://search.api.careerjet.net/v4/query",
                params={
                    "locale_code": "pt_BR",
                    "keywords": "desenvolvedor",
                    "location": "Brasil",
                    "user_ip": "127.0.0.1",
                    "user_agent": "HirePilot/1.5",
                },
                auth=(key, ""),
            )
        latency = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            return _entry("careerjet", "ok", "API respondendo", latency_ms=latency)
        if resp.status_code in {401, 403}:
            return _entry("careerjet", "down", "Chave de API inválida", latency_ms=latency)
        return _entry("careerjet", "degraded", f"HTTP {resp.status_code}", latency_ms=latency)
    except Exception as exc:
        return _entry("careerjet", "down", str(exc)[:120])


def check_empregoscom_health() -> dict[str, Any]:
    try:
        code, latency = _timed_get("https://www.empregos.com.br/")
        if code == 200:
            return _entry("empregoscom", "ok", "Site respondendo", latency_ms=latency)
        if code >= 500:
            return _entry("empregoscom", "down", f"Site retornou HTTP {code}", latency_ms=latency)
        return _entry("empregoscom", "degraded", f"HTTP {code}", latency_ms=latency)
    except Exception as exc:
        return _entry("empregoscom", "down", str(exc)[:120])


def check_trabalhabrasil_health() -> dict[str, Any]:
    ready, msg = _playwright_ready()
    if not ready:
        return _entry("trabalhabrasil", "unavailable", msg)
    try:
        code, latency = _timed_get("https://trabalhabrasil.com.br/")
        if code >= 500:
            return _entry("trabalhabrasil", "down", f"Site retornou HTTP {code}", latency_ms=latency)
        return _entry(
            "trabalhabrasil",
            "browser",
            "Disponível via navegador (scraping na busca)",
            latency_ms=latency,
        )
    except Exception as exc:
        return _entry("trabalhabrasil", "down", str(exc)[:120])


def check_linkedin_health(settings: Settings) -> dict[str, Any]:
    ready, msg = _playwright_ready()
    if not ready:
        return _entry("linkedin", "unavailable", msg)

    try:
        from playwright.sync_api import sync_playwright

        settings.browser_data_dir.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(settings.browser_data_dir),
                headless=True,
                viewport={"width": 900, "height": 700},
                locale="pt-BR",
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=int(_HEALTH_TIMEOUT * 1000),
            )
            cookies = ctx.cookies("https://www.linkedin.com")
            url = page.url
            ctx.close()
        latency = int((time.perf_counter() - t0) * 1000)
        has_session = any(c.get("name") == "li_at" and c.get("value") for c in cookies)
        if has_session:
            return _entry("linkedin", "ok", "Sessão ativa", latency_ms=latency)
        if "/login" in url or "/checkpoint" in url or "/authwall" in url:
            return _entry(
                "linkedin",
                "needs_login",
                "Faça login manual na 1ª busca",
                latency_ms=latency,
            )
        return _entry(
            "linkedin",
            "degraded",
            "Sessão incerta — faça login ou teste uma busca",
            latency_ms=latency,
        )
    except Exception as exc:
        return _entry("linkedin", "down", str(exc)[:120])


_CHECKERS: dict[str, Any] = {
    "gupy": check_gupy_health,
    "indeed": check_indeed_health,
    "greenhouse": check_greenhouse_health,
    "remotive": check_remotive_health,
    "remoteok": check_remoteok_health,
    "infojobs": check_infojobs_health,
    "solides": check_solides_health,
    "trampos": check_trampos_health,
    "catho": check_catho_health,
    "careerjet": check_careerjet_health,
    "empregoscom": check_empregoscom_health,
    "trabalhabrasil": check_trabalhabrasil_health,
}


def check_source_health(source: str, settings: Settings | None = None) -> dict[str, Any]:
    if source == "linkedin":
        return check_linkedin_health(settings or get_settings())
    if source == "vagascom":
        return check_vagascom_health(settings or get_settings())
    if source == "jooble":
        return check_jooble_health(settings)
    if source == "careerjet":
        return check_careerjet_health(settings)
    fn = _CHECKERS.get(source)
    if not fn:
        return _entry(source, "unavailable", "Fonte desconhecida")
    return fn()


def check_all_sources_health(
    settings: Settings | None = None,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    now = time.time()
    with _CACHE_LOCK:
        if not force and _HEALTH_CACHE["sources"] and now - _HEALTH_CACHE["at"] < CACHE_TTL_SECONDS:
            return list(_HEALTH_CACHE["sources"])

    sources = [
        s for s in AVAILABLE_SOURCES
        if s in _CHECKERS or s in ("linkedin", "jooble", "vagascom")
    ]
    results: dict[str, dict[str, Any]] = {}

    def run(name: str) -> dict[str, Any]:
        try:
            return check_source_health(name, settings)
        except Exception as exc:
            logger.warning("Health check %s falhou: %s", name, exc)
            return _entry(name, "down", str(exc)[:120])

    with ThreadPoolExecutor(max_workers=min(7, len(sources))) as pool:
        futures = {pool.submit(run, name): name for name in sources}
        for fut in as_completed(futures):
            item = fut.result()
            results[item["source"]] = item

    ordered = [results[name] for name in sources if name in results]
    with _CACHE_LOCK:
        _HEALTH_CACHE["at"] = now
        _HEALTH_CACHE["sources"] = ordered
    return ordered


def health_summary(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in sources:
        st = item.get("status", "down")
        counts[st] = counts.get(st, 0) + 1
    return counts
