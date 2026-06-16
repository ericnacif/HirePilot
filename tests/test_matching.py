"""Testes do matching perfil x vaga (sem depender do modelo semântico)."""

from cv_apply.matching import (
    _keyword_overlap,
    _location_score,
    _seniority_score,
    apply_keyword_boost,
    match_job,
    rank_jobs,
)
from cv_apply.profile import CandidateProfile, JobPosting


def _job(title="Dev", company="Acme", description="", location=""):
    return JobPosting(
        id="1", title=title, company=company, url="http://x",
        description=description, location=location,
    )


def test_keyword_overlap_inclui_simbolos():
    profile = CandidateProfile(skills=["c++", "python", "react"])
    job = _job(description="Buscamos alguém com C++ e Python.")
    ratio, matched = _keyword_overlap(profile, job)
    assert "c++" in matched
    assert "python" in matched
    assert "react" not in matched
    assert 0 < ratio <= 1


def test_keyword_overlap_sem_skills():
    ratio, matched = _keyword_overlap(CandidateProfile(), _job(description="python"))
    assert ratio == 0.0
    assert matched == []


def test_seniority_score():
    profile = CandidateProfile(seniority="júnior")
    assert _seniority_score(profile, _job(title="Dev Júnior")) == 1.0
    # júnior x vaga sênior recebe penalidade
    assert _seniority_score(profile, _job(title="Senior Engineer")) < 0.5
    # sem senioridade no perfil → neutro
    assert _seniority_score(CandidateProfile(), _job()) == 0.5


def test_location_score():
    profile = CandidateProfile(locations=["São Paulo"])
    assert _location_score(profile, _job(location="Remoto")) == 1.0
    assert _location_score(profile, _job(location="São Paulo")) == 1.0
    assert _location_score(profile, _job(location="")) == 0.5


def test_match_job_sem_semantico_gera_score_e_motivos():
    profile = CandidateProfile(skills=["python"], seniority="júnior")
    job = _job(title="Dev Júnior", description="python")
    m = match_job(profile, job, use_semantic=False)
    assert 0 <= m.score <= 100
    assert m.reasons
    assert "python" in m.skill_overlap


def test_rank_jobs_ordena_decrescente():
    profile = CandidateProfile(skills=["python", "django"])
    jobs = [
        _job(title="Sem relação", description="vendas e marketing"),
        _job(title="Python Dev", description="python e django"),
    ]
    ranked = rank_jobs(profile, jobs, use_semantic=False)
    assert len(ranked) == 2
    assert ranked[0].score >= ranked[1].score
    assert ranked[0].job.title == "Python Dev"


def test_rank_jobs_filtra_min_score():
    profile = CandidateProfile(skills=["python"])
    jobs = [_job(description="nada a ver")]
    assert rank_jobs(profile, jobs, min_score=90, use_semantic=False) == []


def test_rank_jobs_vazio():
    assert rank_jobs(CandidateProfile(), [], use_semantic=False) == []


def test_apply_keyword_boost_prioriza_termo():
    from cv_apply.profile import JobMatch

    a = JobMatch(job=_job("Dev Java"), score=50.0, reasons=[], skill_overlap=[])
    b = JobMatch(
        job=_job("Dev PHP", description="Laravel e PHP"),
        score=50.0, reasons=[], skill_overlap=[],
    )
    ranked = apply_keyword_boost([a, b], "php")
    assert ranked[0].job.title == "Dev PHP"
    assert ranked[0].score > ranked[1].score
