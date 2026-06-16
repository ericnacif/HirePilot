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

_BRAZIL_HINTS = ("brasil", "brazil", "br ", " - br", "(br)")

_BRAZIL_STATES = (
    "acre", "alagoas", "amapa", "amazonas", "bahia", "ceara", "distrito federal",
    "espirito santo", "goias", "maranhao", "mato grosso", "mato grosso do sul",
    "minas gerais", "para", "paraiba", "parana", "pernambuco", "piaui",
    "rio de janeiro", "rio grande do norte", "rio grande do sul",
    "rondonia", "roraima", "santa catarina", "sao paulo", "sergipe", "tocantins",
)

_FOREIGN_LOCATION_HINTS = (
    "usa", "united states", "u.s.", "uk", "united kingdom", "london", "germany",
    "berlin", "france", "paris", "canada", "toronto", "india", "mexico", "méxico",
    "argentina", "chile", "colombia", "portugal", "lisboa", "europe", "europa",
    "asia", "africa", "australia", "japan", "tokyo", "china", "singapore",
)


def _location_matches_wanted(job_location: str, wanted: str) -> bool:
    """True se a localização da vaga é compatível com o filtro do usuário."""
    loc = _strip_accents((job_location or "").strip())
    if not loc:
        return True  # sem localização → não descarta

    if any(h in loc for h in _REMOTE_LOCATION_HINTS):
        return True

    want = _strip_accents((wanted or "").strip())
    if not want or want in ("qualquer", "anywhere", "global", "mundo"):
        return True

    if want in ("brasil", "brazil"):
        if any(h in loc for h in _BRAZIL_HINTS):
            return True
        if any(st in loc for st in _BRAZIL_STATES):
            return True
        if re.search(
            r"\b(sp|rj|mg|pr|rs|sc|ba|pe|ce|df|go|es|am|pa|ma|mt|ms|pb|rn|al|se|pi|ro|ac|ap|rr|to)\b",
            loc,
        ):
            return True
        if any(f in loc for f in _FOREIGN_LOCATION_HINTS):
            return False
        # Gupy costuma usar "Cidade, Estado" — sem sinal estrangeiro, assume BR
        if "," in loc:
            return True
        return want in loc

    return want in loc


def filter_by_location(
    jobs: list[JobPosting], location: str, *, fallback: bool = True
) -> list[JobPosting]:
    """Mantém vagas cuja localização combina com ``location`` (ex.: Brasil, SP).

    Vagas remotas passam sempre. Se o filtro eliminar tudo e ``fallback`` for
    verdadeiro, devolve a lista original.
    """
    wanted = (location or "").strip()
    if not wanted or _strip_accents(wanted) in ("qualquer", "anywhere", "global"):
        return jobs

    kept = [j for j in jobs if _location_matches_wanted(j.location, wanted)]
    if kept or not fallback:
        return kept
    return jobs


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
