"""Geração de currículo adaptado por vaga (rascunho), local e sem LLM.

A adaptação é baseada em palavras-chave: prioriza as skills que a vaga pede,
sugere termos a incluir e monta um resumo direcionado. É um RASCUNHO para você
revisar — não substitui seu currículo, serve de guia para ajustá-lo à vaga.
"""

from __future__ import annotations

import re
from pathlib import Path

from cv_apply.ats import analyze_ats, extract_job_keywords
from cv_apply.profile import CandidateProfile, JobPosting


def _slug(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:40] or "vaga"


def _prioritized_skills(profile: CandidateProfile, job: JobPosting) -> tuple[list[str], list[str]]:
    """Separa skills do candidato em (relevantes p/ vaga, demais)."""
    job_keywords = {k.lower() for k in extract_job_keywords(job)}
    relevant = [s for s in profile.skills if s.lower() in job_keywords]
    others = [s for s in profile.skills if s.lower() not in job_keywords]
    return relevant, others


def _tailored_summary(profile: CandidateProfile, job: JobPosting, relevant: list[str]) -> str:
    seniority = profile.seniority or "profissional"
    role = job.title
    skills_txt = ", ".join(relevant[:6]) if relevant else ", ".join(profile.skills[:6])
    exp = (
        f"{profile.years_experience} anos de experiência"
        if profile.years_experience
        else "experiência na área"
    )
    base = (
        f"{seniority.capitalize()} com {exp}, com foco em {skills_txt}. "
        f"Interesse na vaga de {role}"
    )
    if job.company:
        base += f" na {job.company}"
    base += ", contribuindo com entregas de qualidade e evolução técnica contínua."
    return base


def tailor_resume_markdown(
    profile: CandidateProfile,
    job: JobPosting,
    resume_path: Path | None = None,
) -> str:
    relevant, others = _prioritized_skills(profile, job)
    report = analyze_ats(profile, job, resume_path)
    summary = _tailored_summary(profile, job, relevant)

    lines: list[str] = []
    lines.append(f"# Currículo adaptado — {job.title}")
    lines.append("")
    lines.append(f"> Vaga: **{job.title}** @ **{job.company}**  ")
    lines.append(f"> ATS score estimado: **{report.ats_score:.0f}/100** "
                 f"(cobertura de palavras-chave: {report.keyword_coverage:.0f}%)  ")
    lines.append("> _Rascunho gerado automaticamente. Revise antes de usar._")
    lines.append("")

    # Contato
    lines.append("## Contato")
    if profile.name:
        lines.append(f"- **{profile.name}**")
    if profile.email:
        lines.append(f"- {profile.email}")
    if profile.phone:
        lines.append(f"- {profile.phone}")
    if profile.locations:
        lines.append(f"- {', '.join(profile.locations)}")
    lines.append("")

    # Resumo adaptado
    lines.append("## Resumo profissional (adaptado para a vaga)")
    lines.append(summary)
    lines.append("")

    # Skills priorizadas
    lines.append("## Competências relevantes para esta vaga")
    if relevant:
        lines.append(", ".join(relevant))
    else:
        lines.append("_Nenhuma skill do currículo bateu diretamente com a vaga. "
                     "Revise a descrição e destaque o que for compatível._")
    lines.append("")

    if others:
        lines.append("## Outras competências")
        lines.append(", ".join(others))
        lines.append("")

    # Palavras-chave a incluir
    if report.missing_keywords:
        lines.append("## Palavras-chave da vaga a considerar incluir")
        lines.append("_Inclua apenas as que você realmente domina:_")
        lines.append("")
        for kw in report.missing_keywords[:15]:
            lines.append(f"- [ ] {kw}")
        lines.append("")

    # Sugestões ATS
    if report.suggestions:
        lines.append("## Sugestões ATS")
        for s in report.suggestions:
            lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines)


def save_tailored_resume(
    profile: CandidateProfile,
    job: JobPosting,
    out_dir: Path,
    resume_path: Path | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    content = tailor_resume_markdown(profile, job, resume_path)
    filename = f"{_slug(job.company)}_{_slug(job.title)}.md"
    out_path = out_dir / filename
    out_path.write_text(content, encoding="utf-8")
    return out_path
