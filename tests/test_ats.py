"""Testes da análise ATS (cobertura de palavras-chave e sugestões)."""

from cv_apply.ats import aggregate_missing_keywords, analyze_ats, extract_job_keywords
from cv_apply.profile import CandidateProfile, JobPosting


def _job(description):
    return JobPosting(id="1", title="Dev", company="Acme", url="http://x", description=description)


def test_extract_job_keywords():
    kws = extract_job_keywords(_job("Procuramos dev com Python, Docker e c++."))
    assert "python" in kws
    assert "docker" in kws
    assert "c++" in kws


def test_analyze_ats_present_e_missing():
    profile = CandidateProfile(skills=["python"], raw_text="experiência em python")
    report = analyze_ats(profile, _job("Python e Kubernetes obrigatórios"))
    assert "python" in report.present_keywords
    assert "kubernetes" in report.missing_keywords
    assert 0 <= report.keyword_coverage <= 100


def test_analyze_ats_sem_keywords_da_vaga():
    profile = CandidateProfile(skills=["python"], raw_text="python")
    report = analyze_ats(profile, _job("texto sem tecnologias do dicionário"))
    assert report.keyword_coverage == 0.0
    assert report.ats_score >= 0


def test_analyze_ats_gera_sugestoes_quando_falta():
    profile = CandidateProfile(skills=[], raw_text="")
    report = analyze_ats(profile, _job("Python, Docker, AWS"))
    assert report.suggestions


def test_analyze_ats_title_and_seniority_components():
    profile = CandidateProfile(
        skills=["python", "django"],
        raw_text="desenvolvedor python django",
        job_titles=["Desenvolvedor Python"],
        seniority="júnior",
    )
    job = JobPosting(
        id="1", title="Desenvolvedor Python Júnior", company="X", url="u",
        description="Python Django REST",
    )
    report = analyze_ats(profile, job)
    assert report.title_alignment >= 50
    assert report.seniority_alignment >= 80
    assert report.ats_score > report.keyword_coverage * 0.5


def test_aggregate_missing_keywords():
    profile = CandidateProfile(skills=[], raw_text="")
    r1 = analyze_ats(profile, _job("Python e Docker"))
    r2 = analyze_ats(profile, _job("Python e AWS"))
    agg = dict(aggregate_missing_keywords([r1, r2]))
    assert agg.get("python") == 2
