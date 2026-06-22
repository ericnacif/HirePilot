"""Análise ATS (Applicant Tracking System) do currículo, local e sem LLM.

Faz duas coisas:
1. Cobertura de palavras-chave: compara skills/termos da vaga com o currículo.
2. Checagem de formato: verifica problemas comuns que quebram leitores ATS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from cv_apply.profile import CandidateProfile, JobPosting
from cv_apply.relevance import detect_seniority_levels
from cv_apply.skills_dict import find_skills, text_has_skill

_GENERIC_TITLE_WORDS = {
    "desenvolvedor", "desenvolvedora", "developer", "dev", "programador",
    "programadora", "analista", "analyst", "engenheiro", "engenheira",
    "engineer", "especialista", "specialist", "assistente", "assistant",
    "tecnico", "technician", "consultor", "consultant", "coordenador",
    "gerente", "manager", "vaga", "vagas", "de", "da", "do", "para", "em",
    "jr", "sr", "pl", "pleno", "plena", "junior", "júnior", "senior", "sênior",
}


@dataclass
class FormatCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ATSReport:
    job: JobPosting
    job_keywords: list[str] = field(default_factory=list)
    present_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    keyword_coverage: float = 0.0  # 0-100
    format_checks: list[FormatCheck] = field(default_factory=list)
    format_score: float = 0.0  # 0-100
    title_alignment: float = 0.0  # 0-100
    seniority_alignment: float = 0.0  # 0-100
    ats_score: float = 0.0  # 0-100
    suggestions: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _fallback_job_terms(job: JobPosting) -> list[str]:
    """Termos do título quando o dicionário não encontra skills."""
    tokens = re.split(r"[\s,/\-|]+", _normalize(job.title))
    terms: list[str] = []
    for tok in tokens:
        tok = tok.strip()
        if len(tok) < 3 or tok in _GENERIC_TITLE_WORDS:
            continue
        terms.append(tok)
    return list(dict.fromkeys(terms))[:8]


def extract_job_keywords(job: JobPosting) -> list[str]:
    """Extrai skills/tecnologias mencionadas na vaga usando o dicionário."""
    title_first = find_skills(job.title)
    body = find_skills(f"{job.description or ''}")
    merged: list[str] = []
    seen: set[str] = set()
    for kw in title_first + body:
        key = kw.lower()
        if key not in seen:
            seen.add(key)
            merged.append(kw)
    if not merged:
        merged = _fallback_job_terms(job)
    return merged[:25]


def _keyword_weights(job: JobPosting, job_keywords: list[str]) -> dict[str, float]:
    title_norm = _normalize(job.title)
    desc_norm = _normalize(job.description or "")
    weights: dict[str, float] = {}
    for kw in job_keywords:
        kl = kw.lower()
        weight = 1.0
        if kl in title_norm:
            weight = 2.0
        elif kl in desc_norm[:900]:
            weight = 1.35
        weights[kw] = weight
    return weights


def _keyword_coverage(
    profile: CandidateProfile, job: JobPosting
) -> tuple[list[str], list[str], list[str], float]:
    job_keywords = extract_job_keywords(job)
    if not job_keywords:
        return [], [], [], 0.0

    profile_skills = {s.lower() for s in profile.skills}
    profile_text = _normalize(profile.raw_text)
    weights = _keyword_weights(job, job_keywords)

    present: list[str] = []
    missing: list[str] = []
    weighted_total = 0.0
    weighted_present = 0.0

    for kw in job_keywords:
        weight = weights.get(kw, 1.0)
        weighted_total += weight
        in_skills = kw.lower() in profile_skills
        in_text = text_has_skill(kw, profile_text)
        if in_skills or in_text:
            present.append(kw)
            weighted_present += weight
        else:
            missing.append(kw)

    coverage = (weighted_present / weighted_total * 100) if weighted_total else 0.0
    return job_keywords, present, missing, round(coverage, 1)


def _title_alignment(profile: CandidateProfile, job: JobPosting) -> float:
    job_words = {
        w for w in re.split(r"[\s,/\-|]+", _normalize(job.title))
        if len(w) >= 3 and w not in _GENERIC_TITLE_WORDS
    }
    if not job_words:
        return 50.0

    best = 0.0
    candidates = list(profile.job_titles)
    if profile.headline:
        candidates.append(profile.headline)
    for title in candidates:
        words = {
            w for w in re.split(r"[\s,/\-|]+", _normalize(title))
            if len(w) >= 3 and w not in _GENERIC_TITLE_WORDS
        }
        if not words:
            continue
        overlap = len(words & job_words) / len(job_words)
        best = max(best, overlap)

    if best == 0.0 and profile.skills:
        skill_hits = sum(1 for w in job_words if any(text_has_skill(w, s) for s in profile.skills))
        best = skill_hits / len(job_words) * 0.6

    return round(min(100.0, max(0.0, best * 100)), 1)


def _seniority_alignment(profile: CandidateProfile, job: JobPosting) -> float:
    from cv_apply.relevance import _PROFILE_TO_LEVEL

    if not profile.seniority:
        return 50.0

    prof_level = _PROFILE_TO_LEVEL.get(profile.seniority.strip().lower())
    if not prof_level:
        return 50.0

    job_levels = detect_seniority_levels(job.title)
    if not job_levels:
        job_levels = detect_seniority_levels((job.description or "")[:800])
    if not job_levels:
        return 50.0
    if prof_level in job_levels:
        return 100.0

    junior_wants = prof_level in {"junior", "estagio"}
    senior_job = bool(job_levels & {"senior", "pleno"})
    if junior_wants and senior_job:
        return 15.0
    if prof_level == "senior" and job_levels & {"junior", "estagio"}:
        return 35.0
    return 40.0


def _compose_ats_score(
    coverage: float,
    format_score: float,
    title_alignment: float,
    seniority_alignment: float,
    *,
    has_format: bool,
) -> float:
    if has_format:
        score = (
            coverage * 0.45
            + format_score * 0.25
            + title_alignment * 0.15
            + seniority_alignment * 0.15
        )
    else:
        score = coverage * 0.60 + title_alignment * 0.25 + seniority_alignment * 0.15
    return round(min(100.0, max(0.0, score)), 1)


def analyze_resume_format(resume_path: Path, raw_text: str, profile: CandidateProfile) -> list[FormatCheck]:
    """Checagens de formato que costumam afetar leitores ATS."""
    checks: list[FormatCheck] = []
    text = raw_text or ""
    norm = _normalize(text)
    word_count = len(text.split())

    checks.append(FormatCheck(
        "Email presente",
        bool(profile.email),
        profile.email or "Não encontrado — ATS pode não identificar contato",
    ))
    checks.append(FormatCheck(
        "Telefone presente",
        bool(profile.phone),
        profile.phone or "Não encontrado",
    ))

    section_groups = {
        "Experiência": ["experiência", "experiencia", "experience", "profissional", "atuação"],
        "Formação/Educação": ["formação", "formacao", "educação", "educacao", "education", "acadêmica", "academica", "escolaridade"],
        "Habilidades/Skills": ["habilidades", "competências", "competencias", "skills", "tecnologias", "conhecimentos"],
    }
    for section, keywords in section_groups.items():
        present = any(kw in norm for kw in keywords)
        checks.append(FormatCheck(
            f"Seção '{section}'",
            present,
            "Encontrada" if present else "Não encontrada — adicione um título de seção claro",
        ))

    good_length = 150 <= word_count <= 1500
    checks.append(FormatCheck(
        "Tamanho adequado",
        good_length,
        f"{word_count} palavras"
        + ("" if good_length else " — ideal entre 150 e 1500"),
    ))

    enough_text = word_count >= 80
    checks.append(FormatCheck(
        "Texto extraível",
        enough_text,
        "OK" if enough_text else "Pouco texto — currículo pode estar como imagem (ruim p/ ATS)",
    ))

    if resume_path.suffix.lower() == ".pdf":
        image_count = _count_pdf_images(resume_path)
        checks.append(FormatCheck(
            "Sem excesso de imagens",
            image_count <= 1,
            "OK" if image_count <= 1 else f"{image_count} imagens — evite fotos/ícones, ATS ignora",
        ))

    return checks


def _count_pdf_images(path: Path) -> int:
    try:
        import pdfplumber

        total = 0
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                total += len(page.images or [])
        return total
    except Exception:
        return 0


def analyze_ats(
    profile: CandidateProfile,
    job: JobPosting,
    resume_path: Path | None = None,
) -> ATSReport:
    job_keywords, present, missing, coverage = _keyword_coverage(profile, job)
    title_alignment = _title_alignment(profile, job)
    seniority_alignment = _seniority_alignment(profile, job)

    format_checks: list[FormatCheck] = []
    if resume_path and resume_path.exists():
        format_checks = analyze_resume_format(resume_path, profile.raw_text, profile)

    if format_checks:
        passed = sum(1 for c in format_checks if c.passed)
        format_score = round(passed / len(format_checks) * 100, 1)
    else:
        format_score = 0.0

    ats_score = _compose_ats_score(
        coverage,
        format_score,
        title_alignment,
        seniority_alignment,
        has_format=bool(format_checks),
    )

    suggestions = _build_suggestions(
        missing, format_checks, coverage, title_alignment, seniority_alignment,
    )

    return ATSReport(
        job=job,
        job_keywords=job_keywords,
        present_keywords=present,
        missing_keywords=missing,
        keyword_coverage=coverage,
        format_checks=format_checks,
        format_score=format_score,
        title_alignment=title_alignment,
        seniority_alignment=seniority_alignment,
        ats_score=ats_score,
        suggestions=suggestions,
    )


def analyze_job_requirements(job: JobPosting) -> dict:
    """Resumo da vaga (sem currículo) — útil no modo visitante."""
    keywords = extract_job_keywords(job)
    levels = detect_seniority_levels(job.title) or detect_seniority_levels((job.description or "")[:800])
    level_label = ", ".join(sorted(levels)) if levels else None
    return {
        "job_keywords": keywords,
        "seniority": level_label,
        "needs_resume": True,
    }


def _build_suggestions(
    missing: list[str],
    format_checks: list[FormatCheck],
    coverage: float,
    title_alignment: float,
    seniority_alignment: float,
) -> list[str]:
    suggestions: list[str] = []

    if missing:
        top_missing = ", ".join(missing[:8])
        suggestions.append(
            f"Inclua (se você tiver) estas palavras-chave da vaga: {top_missing}"
        )
    if coverage >= 80:
        suggestions.append("Boa cobertura de palavras-chave para esta vaga.")
    elif coverage < 50 and missing:
        suggestions.append(
            "Cobertura baixa: adapte o currículo destacando as skills que a vaga pede."
        )

    if title_alignment < 45:
        suggestions.append(
            "O cargo atual do currículo parece distante do título da vaga — ajuste o headline ou o resumo."
        )
    if seniority_alignment < 40:
        suggestions.append(
            "O nível de senioridade da vaga pode não combinar com o seu perfil."
        )

    for check in format_checks:
        if not check.passed:
            suggestions.append(f"Formato: {check.name} — {check.detail}")

    return suggestions


def aggregate_missing_keywords(reports: list[ATSReport], top: int = 15) -> list[tuple[str, int]]:
    """Palavras-chave que mais faltam considerando várias vagas."""
    counter: dict[str, int] = {}
    for report in reports:
        for kw in report.missing_keywords:
            counter[kw] = counter.get(kw, 0) + 1
    ordered = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    return ordered[:top]
