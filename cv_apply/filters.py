"""Mapeamento de filtros de busca (valores em PT) para cada plataforma.

Valores aceitos no .env:
- SEARCH_WORKPLACE: remoto, hibrido, presencial
- SEARCH_JOB_TYPE:  efetivo, estagio, meio_periodo, temporario, pj
- SEARCH_EXPERIENCE: estagio, junior, pleno, senior, diretor, executivo
- SEARCH_DATE_POSTED: 24h, semana, mes, qualquer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# LinkedIn: f_WT (workplace type)
_LINKEDIN_WORKPLACE = {"presencial": "1", "remoto": "2", "hibrido": "3"}
# LinkedIn: f_JT (job type)
_LINKEDIN_JOB_TYPE = {
    "efetivo": "F",
    "meio_periodo": "P",
    "pj": "C",
    "contrato": "C",
    "temporario": "T",
    "estagio": "I",
}
# LinkedIn: f_E (experience level)
_LINKEDIN_EXPERIENCE = {
    "estagio": "1",
    "junior": "2",
    "pleno": "3",
    "senior": "4",
    "diretor": "5",
    "executivo": "6",
}
# LinkedIn: f_TPR (date posted, em segundos)
_LINKEDIN_DATE = {
    "24h": "r86400",
    "semana": "r604800",
    "mes": "r2592000",
}

# Mapeamento de tipos da Gupy (campo `type`)
_GUPY_JOB_TYPE = {
    "efetivo": "vacancy_type_effective",
    "estagio": "vacancy_type_internship",
    "temporario": "vacancy_type_temporary",
    "pj": "vacancy_type_outsource",
    "trainee": "vacancy_type_trainee",
}
# Mapeamento de workplaceType da Gupy
_GUPY_WORKPLACE = {"remoto": "remote", "hibrido": "hybrid", "presencial": "on-site"}

# Remotive/RemoteOK: tipos
_GENERIC_JOB_TYPE = {
    "efetivo": ["full_time", "full-time", "fulltime"],
    "meio_periodo": ["part_time", "part-time"],
    "estagio": ["internship", "intern"],
    "temporario": ["temporary", "contract"],
    "pj": ["contract", "freelance"],
}

_DATE_DELTAS = {
    "24h": timedelta(days=1),
    "semana": timedelta(days=7),
    "mes": timedelta(days=30),
}


@dataclass
class SearchFilters:
    keywords: str = ""
    location: str = ""
    workplace: list[str] = field(default_factory=list)
    job_type: list[str] = field(default_factory=list)
    experience: list[str] = field(default_factory=list)
    date_posted: str = "qualquer"

    @classmethod
    def from_settings(cls, settings) -> "SearchFilters":
        return cls(
            keywords=settings.search_keywords,
            location=settings.search_location,
            workplace=list(settings.search_workplace),
            job_type=list(settings.search_job_type),
            experience=list(settings.search_experience),
            date_posted=settings.search_date_posted,
        )

    # ----- LinkedIn -----
    def linkedin_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        wt = [_LINKEDIN_WORKPLACE[w] for w in self.workplace if w in _LINKEDIN_WORKPLACE]
        if wt:
            params["f_WT"] = ",".join(wt)
        jt = [_LINKEDIN_JOB_TYPE[j] for j in self.job_type if j in _LINKEDIN_JOB_TYPE]
        if jt:
            params["f_JT"] = ",".join(dict.fromkeys(jt))
        exp = [_LINKEDIN_EXPERIENCE[e] for e in self.experience if e in _LINKEDIN_EXPERIENCE]
        if exp:
            params["f_E"] = ",".join(exp)
        if self.date_posted in _LINKEDIN_DATE:
            params["f_TPR"] = _LINKEDIN_DATE[self.date_posted]
        return params

    # ----- Gupy -----
    def gupy_workplace_types(self) -> list[str]:
        return [_GUPY_WORKPLACE[w] for w in self.workplace if w in _GUPY_WORKPLACE]

    def gupy_job_types(self) -> list[str]:
        return [_GUPY_JOB_TYPE[j] for j in self.job_type if j in _GUPY_JOB_TYPE]

    def only_remote(self) -> bool:
        return self.workplace == ["remoto"]

    def allows_remote(self) -> bool:
        return (not self.workplace) or ("remoto" in self.workplace)

    # ----- Filtragem client-side (genérica) -----
    def generic_job_type_terms(self) -> list[str]:
        terms: list[str] = []
        for j in self.job_type:
            terms.extend(_GENERIC_JOB_TYPE.get(j, []))
        return terms

    def date_cutoff(self) -> datetime | None:
        delta = _DATE_DELTAS.get(self.date_posted)
        if not delta:
            return None
        return datetime.now(timezone.utc) - delta

    def matches_date(self, published: datetime | None) -> bool:
        cutoff = self.date_cutoff()
        if cutoff is None or published is None:
            return True
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return published >= cutoff

    def matches_generic_job_type(self, job_type_value: str) -> bool:
        terms = self.generic_job_type_terms()
        if not terms:
            return True
        value = (job_type_value or "").lower().replace(" ", "_")
        return any(t.replace(" ", "_") in value or value in t for t in terms)
