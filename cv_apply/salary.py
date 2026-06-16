"""Extração e filtro de faixa salarial a partir do texto da vaga."""

from __future__ import annotations

import re

from cv_apply.profile import JobPosting

# Valores mensais em BRL (heurística para vagas BR)
_BRL_PATTERNS = [
    re.compile(
        r"R\$\s*([\d.,]+)\s*(?:a|[-–])\s*R\$\s*([\d.,]+)",
        re.I,
    ),
    re.compile(r"R\$\s*([\d.,]+)", re.I),
    re.compile(
        r"([\d.,]+)\s*(?:a|[-–])\s*([\d.,]+)\s*reais",
        re.I,
    ),
]

_USD_PATTERNS = [
    re.compile(
        r"(?<!R)\$\s*([\d,]+(?:\.\d+)?)\s*k?\s*(?:a|[-–to]+)\s*\$?\s*([\d,]+(?:\.\d+)?)\s*k?",
        re.I,
    ),
    re.compile(r"(?<!R)\$\s*([\d,]+(?:\.\d+)?)\s*k\b", re.I),
    re.compile(r"USD\s*([\d,]+(?:\.\d+)?)\s*k?", re.I),
]

_USD_TO_BRL = 5.5  # aproximação para filtro relativo


def _parse_money_br(text: str) -> float | None:
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_money_us(text: str) -> float | None:
    text = text.strip().replace(",", "")
    mult = 1000.0 if text.lower().endswith("k") else 1.0
    text = text.rstrip("kK")
    try:
        return float(text) * mult
    except ValueError:
        return None


def extract_salary(job: JobPosting) -> tuple[float | None, float | None, str | None]:
    """Retorna (min_brl, max_brl, texto) estimados a partir da vaga."""
    hay = f"{job.title} {job.description} {job.location}"
    for pat in _BRL_PATTERNS:
        m = pat.search(hay)
        if not m:
            continue
        groups = m.groups()
        if len(groups) == 2:
            lo = _parse_money_br(groups[0])
            hi = _parse_money_br(groups[1])
            if lo and hi:
                return min(lo, hi), max(lo, hi), m.group(0).strip()
        elif len(groups) == 1:
            val = _parse_money_br(groups[0])
            if val:
                return val, val, m.group(0).strip()

    for pat in _USD_PATTERNS:
        m = pat.search(hay)
        if not m:
            continue
        groups = m.groups()
        if len(groups) == 2:
            lo = _parse_money_us(groups[0])
            hi = _parse_money_us(groups[1])
            if lo and hi:
                lo *= _USD_TO_BRL
                hi *= _USD_TO_BRL
                return min(lo, hi), max(lo, hi), m.group(0).strip()
        elif len(groups) == 1:
            val = _parse_money_us(groups[0])
            if val:
                val *= _USD_TO_BRL
                return val, val, m.group(0).strip()
    return None, None, None


def filter_by_salary(
    jobs: list[JobPosting],
    min_brl: float | None,
    max_brl: float | None,
    *,
    fallback: bool = True,
) -> list[JobPosting]:
    """Mantém vagas cuja faixa salarial estimada intersecta o filtro."""
    if min_brl is None and max_brl is None:
        return jobs

    kept: list[JobPosting] = []
    unknown: list[JobPosting] = []
    for job in jobs:
        lo, hi, _ = extract_salary(job)
        if lo is None and hi is None:
            unknown.append(job)
            continue
        lo = lo or hi or 0.0
        hi = hi or lo or 0.0
        if min_brl is not None and hi < min_brl:
            continue
        if max_brl is not None and lo > max_brl:
            continue
        kept.append(job)

    if kept:
        return kept + unknown  # mantém vagas sem salário junto
    return jobs if fallback else kept
