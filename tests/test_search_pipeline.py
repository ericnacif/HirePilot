"""Testes do pipeline de busca."""

from cv_apply.config import Settings
from cv_apply.profile import CandidateProfile, JobMatch, JobPosting
from cv_apply.search_pipeline import (
    SearchContext,
    apply_display_limits,
    posted_sort_key,
    process_raw_jobs,
)


def _job(job_id: str) -> JobPosting:
    return JobPosting(
        id=job_id,
        title=job_id,
        company="co",
        location="",
        url=f"https://example.com/{job_id}",
    )


def _match(job: JobPosting, score: float) -> JobMatch:
    return JobMatch(job=job, score=score)


def test_posted_sort_key_iso():
    a = posted_sort_key("2026-06-15T10:00:00+00:00")
    b = posted_sort_key("2026-06-01T10:00:00+00:00")
    assert a > b


def test_posted_sort_key_vazio():
    assert posted_sort_key(None) == 0.0
    assert posted_sort_key("") == 0.0


def test_broad_mode_limits_per_source_not_global_top_n():
    jobs = [_job("g1"), _job("g2"), _job("h1")]
    matches = [_match(jobs[0], 90), _match(jobs[1], 80), _match(jobs[2], 95)]
    source_by_id = {"g1": "gupy", "g2": "gupy", "h1": "greenhouse"}
    ctx = SearchContext(broad=True, limit_per_source=1, global_cap=0)
    out, meta = apply_display_limits(matches, source_by_id, ctx)
    assert len(out) == 2
    assert {m.job.id for m in out} == {"g1", "h1"}
    assert meta["truncation"] == "per_source"


def test_broad_mode_honors_explicit_global_cap():
    jobs = [_job(f"j{i}") for i in range(5)]
    matches = [_match(j, float(100 - i)) for i, j in enumerate(jobs)]
    source_by_id = {j.id: "gupy" for j in jobs}
    ctx = SearchContext(broad=True, limit_per_source=10, global_cap=2)
    out, meta = apply_display_limits(matches, source_by_id, ctx)
    assert len(out) == 2
    assert meta["truncation"] == "global_cap"


def test_process_raw_jobs_filtra_senioridade_via_perfil():
    jobs = [
        JobPosting(id="1", title="Dev Júnior", company="X", url="u", description="PHP"),
        JobPosting(id="2", title="Dev Sênior", company="X", url="u", description="PHP"),
    ]
    settings = Settings(search_experience=[], search_location="")
    ctx = SearchContext(user_keywords="php", broad=True)
    profile = CandidateProfile(seniority="júnior")
    out, _also = process_raw_jobs(jobs, ctx, settings, profile)
    titles = [j.title for j in out]
    assert "Dev Júnior" in titles
    assert "Dev Sênior" not in titles


def test_process_raw_jobs_broad_sector_keeps_non_matching_titles():
    """Modo amplo + área sem keywords: não descarta vagas só porque o título não cita a stack."""
    jobs = [
        JobPosting(id="1", title="Software Engineer", company="X", url="u1", description=""),
        JobPosting(id="2", title="Product Designer", company="X", url="u2", description=""),
    ]
    settings = Settings(search_experience=[], search_location="")
    ctx = SearchContext(sector="tec_dev", user_keywords="", broad=True)
    out, _also = process_raw_jobs(jobs, ctx, settings, None)
    assert len(out) == 2


def test_process_raw_jobs_relevancia_php_modo_amplo():
    jobs = [
        JobPosting(id="1", title="Dev PHP", company="X", url="u1", description="PHP"),
        JobPosting(id="2", title="Dev Python", company="X", url="u2", description="Python"),
    ]
    settings = Settings(search_experience=[], search_location="")
    ctx = SearchContext(user_keywords="php", broad=True)
    out, _also = process_raw_jobs(jobs, ctx, settings, None)
    assert len(out) == 1
    assert out[0].title == "Dev PHP"
