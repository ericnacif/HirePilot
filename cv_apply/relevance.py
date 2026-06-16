"""Filtros de relevância pós-busca, aplicados a TODAS as fontes.

As APIs de vagas (Gupy, Remotive, RemoteOK) não filtram por senioridade nem
garantem que o termo procurado realmente apareça. Aqui aplicamos, de forma
uniforme:

- :func:`filter_by_experience` — remove vagas cujo nível (júnior/pleno/sênior)
  contradiz o que o usuário pediu.
- :func:`filter_by_relevance` — mantém apenas vagas que mencionam os termos
  específicos digitados pelo usuário (ex.: "php"), ignorando palavras genéricas
  de cargo.
"""

from __future__ import annotations

import re
import unicodedata

from cv_apply.locations import (
    LocationFilter,
    filter_jobs_by_location,
    job_matches_location,
    parse_location,
)
from cv_apply.profile import JobPosting
from cv_apply.skills_dict import text_has_skill

# Níveis de senioridade e os termos que os indicam (casados com borda de palavra).
_SENIORITY_TERMS: dict[str, list[str]] = {
    "estagio": ["estagio", "estagiario", "estagiaria", "estágio", "intern", "internship", "trainee", "aprendiz"],
    "junior": ["junior", "júnior", "jr", "entry level", "entry-level", "iniciante"],
    "pleno": ["pleno", "plena", "mid level", "mid-level", "intermediate", "intermediario"],
    "senior": ["senior", "sênior", "sr", "lead", "principal", "staff", "especialista", "specialist"],
}

# Palavras de cargo genéricas: não servem como "termo obrigatório" de relevância
# (senão qualquer vaga de dev passaria numa busca por "desenvolvedor php").
_GENERIC_ROLE_WORDS = {
    "desenvolvedor", "desenvolvedora", "developer", "dev", "programador",
    "programadora", "analista", "analyst", "engenheiro", "engenheira",
    "engineer", "especialista", "specialist", "assistente", "assistant",
    "tecnico", "technician", "consultor", "consultant", "coordenador",
    "gerente", "manager", "estagiario", "estagiaria", "trainee", "junior",
    "pleno", "plena", "senior", "jr", "sr", "pl", "full", "stack", "fullstack",
    "software", "vaga", "vagas", "de", "da", "do", "dos", "das", "e", "em",
    "para", "com", "a", "o",
}


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def detect_seniority_levels(text: str) -> set[str]:
    """Níveis de senioridade mencionados em ``text`` (vazio = não identificado)."""
    norm = _strip_accents(text)
    found: set[str] = set()
    for level, terms in _SENIORITY_TERMS.items():
        for term in terms:
            t = _strip_accents(term)
            if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", norm):
                found.add(level)
                break
    return found


def filter_by_experience(
    jobs: list[JobPosting], wanted: list[str]
) -> list[JobPosting]:
    """Remove vagas cujo nível explícito contradiz os níveis desejados.

    - Detecta o nível pelo **título** (sinal mais confiável); se o título não
      indicar nada, olha o início da descrição.
    - Vagas sem nível identificável são mantidas (ambíguas).
    - Vagas com nível identificado só passam se houver interseção com ``wanted``.
    """
    wanted_set = {w.strip().lower() for w in wanted if w.strip()}
    # só conhecemos esses níveis; ignora valores como "diretor"/"executivo"
    wanted_set &= set(_SENIORITY_TERMS.keys())
    if not wanted_set:
        return jobs

    kept: list[JobPosting] = []
    for job in jobs:
        levels = detect_seniority_levels(job.title)
        if not levels:
            levels = detect_seniority_levels((job.description or "")[:200])
        if not levels or (levels & wanted_set):
            kept.append(job)
    return kept


def extract_query_terms(keywords: str) -> list[str]:
    """Termos específicos (não genéricos) digitados pelo usuário, p/ relevância."""
    tokens = re.split(r"[\s,;/]+", (keywords or "").lower())
    terms: list[str] = []
    for tok in tokens:
        tok = tok.strip()
        if len(tok) < 2:
            continue
        if _strip_accents(tok) in _GENERIC_ROLE_WORDS:
            continue
        terms.append(tok)
    return terms


def _term_in_text(term: str, text: str) -> bool:
    if text_has_skill(term, text):
        return True
    return _strip_accents(term) in _strip_accents(text)


def term_in_job_text(term: str, text: str) -> bool:
    """API pública para checar se um termo aparece no texto da vaga."""
    return _term_in_text(term, text)


_REMOTE_LOCATION_HINTS = (
    "remoto", "remote", "home office", "home-office", "anywhere",
    "worldwide", "global", "distributed", "híbrido", "hibrido", "hybrid",
)


def _location_matches_wanted(job_location: str, wanted: str) -> bool:
    """Retrocompat — delega ao módulo de localização."""
    return job_matches_location(job_location, parse_location(wanted))


def filter_by_location(
    jobs: list[JobPosting],
    location: str,
    *,
    fallback: bool = True,
    location_filter: LocationFilter | None = None,
) -> list[JobPosting]:
    """Mantém vagas cuja localização combina com o filtro do usuário."""
    filt = location_filter or parse_location(location or "")
    if filt.scope.value == "any" and not (location or "").strip():
        return jobs
    use_fallback = fallback and not filt.strict
    return filter_jobs_by_location(jobs, filt, fallback=use_fallback)


def filter_by_relevance(
    jobs: list[JobPosting], terms: list[str], fallback: bool = True
) -> list[JobPosting]:
    """Mantém vagas que mencionam ALGUM dos ``terms`` (título ou descrição).

    Se ``fallback`` (padrão) e nenhum termo bater, devolve a lista original
    (evita zerar tudo). Com ``fallback=False``, devolve a lista filtrada mesmo
    que vazia — preferindo "nada encontrado" honesto a resultados irrelevantes.
    """
    if not terms:
        return jobs
    kept = [
        job
        for job in jobs
        if any(_term_in_text(t, f"{job.title} {job.description}") for t in terms)
    ]
    if kept or not fallback:
        return kept
    return jobs
