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
from cv_apply.skills_dict import compile_skill_regex, find_skills


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
    ats_score: float = 0.0  # 0-100
    suggestions: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def extract_job_keywords(job: JobPosting) -> list[str]:
    """Extrai skills/tecnologias mencionadas na vaga usando o dicionário."""
    return find_skills(f"{job.title} {job.description}")


def _keyword_coverage(
    profile: CandidateProfile, job: JobPosting
) -> tuple[list[str], list[str], list[str], float]:
    job_keywords = extract_job_keywords(job)
    profile_skills = {s.lower() for s in profile.skills}
    profile_text = _normalize(profile.raw_text)

    present: list[str] = []
    missing: list[str] = []
    for kw in job_keywords:
        in_skills = kw.lower() in profile_skills
        in_text = compile_skill_regex(kw).search(profile_text) is not None
        if in_skills or in_text:
            present.append(kw)
        else:
            missing.append(kw)

    coverage = (len(present) / len(job_keywords) * 100) if job_keywords else 100.0
    return job_keywords, present, missing, round(coverage, 1)


def analyze_resume_format(resume_path: Path, raw_text: str, profile: CandidateProfile) -> list[FormatCheck]:
    """Checagens de formato que costumam afetar leitores ATS."""
    checks: list[FormatCheck] = []
    text = raw_text or ""
    norm = _normalize(text)
    word_count = len(text.split())

    # Contato
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

    # Seções essenciais
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

    # Tamanho
    good_length = 150 <= word_count <= 1500
    checks.append(FormatCheck(
        "Tamanho adequado",
        good_length,
        f"{word_count} palavras"
        + ("" if good_length else " — ideal entre 150 e 1500"),
    ))

    # Texto extraível (se quase não há texto, provável currículo em imagem)
    enough_text = word_count >= 80
    checks.append(FormatCheck(
        "Texto extraível",
        enough_text,
        "OK" if enough_text else "Pouco texto — currículo pode estar como imagem (ruim p/ ATS)",
    ))

    # Imagens no PDF (logos/fotos podem atrapalhar ATS)
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

    format_checks: list[FormatCheck] = []
    if resume_path and resume_path.exists():
        format_checks = analyze_resume_format(resume_path, profile.raw_text, profile)

    if format_checks:
        passed = sum(1 for c in format_checks if c.passed)
        format_score = round(passed / len(format_checks) * 100, 1)
    else:
        format_score = 0.0

    # ATS score: 65% palavras-chave + 35% formato (se houver checagem)
    if format_checks:
        ats_score = round(coverage * 0.65 + format_score * 0.35, 1)
    else:
        ats_score = coverage

    suggestions = _build_suggestions(missing, format_checks, coverage)

    return ATSReport(
        job=job,
        job_keywords=job_keywords,
        present_keywords=present,
        missing_keywords=missing,
        keyword_coverage=coverage,
        format_checks=format_checks,
        format_score=format_score,
        ats_score=ats_score,
        suggestions=suggestions,
    )


def _build_suggestions(
    missing: list[str], format_checks: list[FormatCheck], coverage: float
) -> list[str]:
    suggestions: list[str] = []

    if missing:
        top_missing = ", ".join(missing[:8])
        suggestions.append(
            f"Inclua (se você tiver) estas palavras-chave da vaga: {top_missing}"
        )
    if coverage >= 80:
        suggestions.append("Boa cobertura de palavras-chave para esta vaga.")
    elif coverage < 50:
        suggestions.append(
            "Cobertura baixa: adapte o currículo destacando as skills que a vaga pede."
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
