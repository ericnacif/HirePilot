"""Parse e filtro de localização para busca de vagas."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from cv_apply.profile import JobPosting

_STATE_NAMES: dict[str, str] = {
    "ac": "acre",
    "al": "alagoas",
    "ap": "amapa",
    "am": "amazonas",
    "ba": "bahia",
    "ce": "ceara",
    "df": "distrito federal",
    "es": "espirito santo",
    "go": "goias",
    "ma": "maranhao",
    "mt": "mato grosso",
    "ms": "mato grosso do sul",
    "mg": "minas gerais",
    "pa": "para",
    "pb": "paraiba",
    "pr": "parana",
    "pe": "pernambuco",
    "pi": "piaui",
    "rj": "rio de janeiro",
    "rn": "rio grande do norte",
    "rs": "rio grande do sul",
    "ro": "rondonia",
    "rr": "roraima",
    "sc": "santa catarina",
    "sp": "sao paulo",
    "se": "sergipe",
    "to": "tocantins",
}

_STATE_UFS = set(_STATE_NAMES.keys())

_REMOTE_HINTS = (
    "remoto", "remote", "home office", "home-office", "anywhere",
    "worldwide", "global", "distributed", "trabalho remoto",
)

_HYBRID_HINTS = ("híbrido", "hibrido", "hybrid")

_BRAZIL_HINTS = ("brasil", "brazil", "br ", " - br", "(br)")

_FOREIGN_HINTS = (
    "usa", "united states", "u.s.", "u.s.a", "uk", "united kingdom", "london",
    "germany", "berlin", "france", "paris", "canada", "toronto", "india",
    "mexico", "méxico", "argentina", "chile", "colombia", "portugal", "lisboa",
    "europe", "europa", "asia", "africa", "australia", "japan", "tokyo",
    "china", "singapore", "ireland", "dublin", "netherlands", "amsterdam",
)


class LocationScope(str, Enum):
    CITY = "city"
    STATE = "state"
    BRAZIL = "br"
    REMOTE = "remote"
    FOREIGN = "foreign"
    ANY = "any"


@dataclass(frozen=True)
class LocationFilter:
    scope: LocationScope = LocationScope.BRAZIL
    city: str = ""
    state: str = ""  # UF
    raw: str = ""
    include_remote: bool = False

    @property
    def is_specific(self) -> bool:
        return self.scope in (LocationScope.CITY, LocationScope.STATE)

    @property
    def strict(self) -> bool:
        return self.scope in (
            LocationScope.CITY,
            LocationScope.STATE,
            LocationScope.FOREIGN,
        )

    def display_label(self) -> str:
        if self.scope == LocationScope.CITY and self.city:
            return f"{self.city}, {self.state}" if self.state else self.city
        if self.scope == LocationScope.STATE and self.state:
            return self.state.upper()
        labels = {
            LocationScope.BRAZIL: "Todo o Brasil",
            LocationScope.REMOTE: "Remoto / home office",
            LocationScope.FOREIGN: "Exterior",
            LocationScope.ANY: "Qualquer lugar",
        }
        return labels.get(self.scope, self.raw or "Brasil")

    def indeed_query(self) -> str:
        if self.scope == LocationScope.CITY:
            if self.city and self.state:
                return f"{self.city}, {self.state}, Brasil"
            return self.city or "Brasil"
        if self.scope == LocationScope.STATE and self.state:
            return f"{_STATE_NAMES.get(self.state.lower(), self.state)}, Brasil"
        if self.scope == LocationScope.FOREIGN:
            return ""
        if self.scope == LocationScope.REMOTE:
            return "Brasil"
        return "Brasil"


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _norm(text: str) -> str:
    return strip_accents((text or "").strip())


def _is_remote_text(text: str) -> bool:
    norm = _norm(text)
    return any(h in norm for h in _REMOTE_HINTS)


def _is_hybrid_text(text: str) -> bool:
    norm = _norm(text)
    return any(h in norm for h in _HYBRID_HINTS)


def _is_foreign_text(text: str) -> bool:
    norm = _norm(text)
    if any(h in norm for h in _BRAZIL_HINTS):
        return False
    return any(h in norm for h in _FOREIGN_HINTS)


def _extract_state_from_location(loc: str) -> str:
    norm = _norm(loc)
    m = re.search(
        r"\b(ac|al|ap|am|ba|ce|df|es|go|ma|mt|ms|mg|pa|pb|pr|pe|pi|rj|rn|rs|ro|rr|sc|sp|se|to)\b",
        norm,
    )
    if m:
        return m.group(1)
    for uf, name in _STATE_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", norm):
            return uf
    return ""


def _city_in_location(city: str, loc: str) -> bool:
    city_n = _norm(city)
    loc_n = _norm(loc)
    if not city_n:
        return True
    if city_n in loc_n:
        return True
    # "São Paulo" vs "Sao Paulo - SP"
    city_compact = re.sub(r"[^a-z0-9]", "", city_n)
    loc_compact = re.sub(r"[^a-z0-9]", "", loc_n)
    return city_compact in loc_compact


def _state_in_location(state: str, loc: str) -> bool:
    uf = (state or "").strip().lower()
    if not uf or uf not in _STATE_UFS:
        return True
    loc_n = _norm(loc)
    if re.search(rf"\b{re.escape(uf)}\b", loc_n):
        return True
    name = _STATE_NAMES.get(uf, "")
    return bool(name and re.search(rf"\b{re.escape(name)}\b", loc_n))


def parse_location(
    raw: str,
    *,
    scope: str | None = None,
    city: str | None = None,
    state: str | None = None,
    include_remote: bool | None = None,
) -> LocationFilter:
    """Interpreta local do usuário (texto livre ou campos estruturados)."""
    scope_raw = (scope or "").strip().lower()
    city_val = (city or "").strip()
    state_val = (state or "").strip().upper()[:2]
    raw_val = (raw or "").strip()

    if scope_raw in {s.value for s in LocationScope}:
        loc_scope = LocationScope(scope_raw)
    else:
        loc_scope = _infer_scope_from_text(raw_val, city_val, state_val)

    if not city_val and not state_val and raw_val:
        parsed_city, parsed_state = _parse_freeform(raw_val)
        city_val = city_val or parsed_city
        state_val = state_val or parsed_state
        if not scope_raw:
            loc_scope = _infer_scope_from_text(raw_val, city_val, state_val)

    if loc_scope == LocationScope.CITY and not city_val and raw_val:
        city_val = raw_val.split(",")[0].strip()

    inc_remote = bool(include_remote)
    if loc_scope == LocationScope.REMOTE:
        inc_remote = True

    return LocationFilter(
        scope=loc_scope,
        city=city_val,
        state=state_val,
        raw=raw_val,
        include_remote=inc_remote,
    )


def _infer_scope_from_text(raw: str, city: str, state: str) -> LocationScope:
    norm = _norm(raw)
    if not norm and not city and not state:
        return LocationScope.BRAZIL
    if norm in ("remoto", "remote", "home office", "home-office", "trabalho remoto"):
        return LocationScope.REMOTE
    if norm in ("exterior", "exterior", "internacional", "foreign", "abroad", "fora do brasil"):
        return LocationScope.FOREIGN
    if norm in ("brasil", "brazil", "todo brasil", "todo o brasil", "qualquer", "anywhere"):
        return LocationScope.BRAZIL
    if city and state:
        return LocationScope.CITY
    if state and not city:
        return LocationScope.STATE
    if "," in raw and _extract_state_from_location(raw):
        return LocationScope.CITY
    if _extract_state_from_location(raw) and len(norm.split()) <= 3:
        return LocationScope.STATE
    if city:
        return LocationScope.CITY
    return LocationScope.BRAZIL


def _parse_freeform(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        return "", ""
    parts = [p.strip() for p in re.split(r"[,;/\-–]", text) if p.strip()]
    if len(parts) >= 2:
        maybe_state = parts[-1].upper()
        if maybe_state.lower() in _STATE_NAMES or maybe_state.lower() in ("brasil", "brazil"):
            if maybe_state.lower() in ("brasil", "brazil"):
                return parts[0], _extract_state_from_location(text) or ""
            return ", ".join(parts[:-1]), maybe_state[:2]
    state = _extract_state_from_location(text)
    city = text
    if state:
        city = re.sub(
            rf"\b{state}\b|{_STATE_NAMES.get(state, '')}",
            "",
            _norm(text),
            flags=re.I,
        ).strip(" ,-/")
        # recover original casing from first segment
        city = parts[0] if parts else text
    return city.strip(), state.upper() if state else ""


def job_matches_location(job_location: str, filt: LocationFilter) -> bool:
    loc = (job_location or "").strip()
    if filt.scope == LocationScope.ANY:
        return True

    remote = _is_remote_text(loc)
    hybrid = _is_hybrid_text(loc)
    foreign = _is_foreign_text(loc)

    if filt.scope == LocationScope.REMOTE:
        return remote or hybrid or (not loc)

    if filt.scope == LocationScope.FOREIGN:
        return foreign and _norm(loc) not in ("brasil", "brazil")

    if filt.scope == LocationScope.BRAZIL:
        if foreign:
            return False
        if remote:
            return True
        if not loc:
            return True
        if any(h in _norm(loc) for h in _BRAZIL_HINTS):
            return True
        if _extract_state_from_location(loc):
            return True
        if "," in loc and not foreign:
            return True
        return _norm("brasil") in _norm(loc) or not foreign

    if filt.scope == LocationScope.STATE:
        if remote or hybrid:
            return filt.include_remote
        if not loc:
            return filt.include_remote
        if foreign:
            return False
        return _state_in_location(filt.state, loc)

    if filt.scope == LocationScope.CITY:
        if remote or hybrid:
            return filt.include_remote
        if not loc:
            return False
        if foreign:
            return False
        city_ok = _city_in_location(filt.city, loc)
        if filt.state:
            return city_ok and _state_in_location(filt.state, loc)
        return city_ok

    return True


def filter_jobs_by_location(
    jobs: list[JobPosting],
    filt: LocationFilter,
    *,
    fallback: bool = False,
) -> list[JobPosting]:
    if filt.scope == LocationScope.ANY:
        return jobs
    kept = [j for j in jobs if job_matches_location(j.location, filt)]
    if kept or not fallback:
        return kept
    return jobs


def location_match_strength(job_location: str, filt: LocationFilter) -> float:
    """0–1 para ranquear vagas mais próximas da localização desejada."""
    loc = job_location or ""
    if not job_matches_location(loc, filt):
        return 0.0
    if filt.scope == LocationScope.CITY:
        if _city_in_location(filt.city, loc) and _state_in_location(filt.state, loc):
            if _is_remote_text(loc):
                return 0.55
            return 1.0
        return 0.4
    if filt.scope == LocationScope.STATE:
        if _state_in_location(filt.state, loc):
            return 0.85 if not _is_remote_text(loc) else 0.5
        return 0.3
    if filt.scope == LocationScope.REMOTE and _is_remote_text(loc):
        return 1.0
    if filt.scope == LocationScope.BRAZIL and not _is_foreign_text(loc):
        return 0.7
    return 0.5


def build_location_string(filt: LocationFilter) -> str:
    return filt.display_label()
