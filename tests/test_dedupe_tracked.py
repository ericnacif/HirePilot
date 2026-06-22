"""Testes de deduplicação com rastreamento de fontes alternativas."""

from cv_apply.profile import JobPosting
from cv_apply.sources import dedupe_jobs_tracked


def _job(job_id: str, url: str, title: str = "Dev", source: str = "") -> JobPosting:
    return JobPosting(
        id=job_id,
        title=title,
        company="Acme",
        location="SP",
        url=url,
        description="",
        easy_apply=False,
    )


def test_dedupe_same_url_tracks_also_in():
    j1 = _job("gupy-1", "https://empresa.gupy.io/jobs/123")
    j2 = _job("indeed-1", "https://empresa.gupy.io/jobs/123")
    source_by_id = {"gupy-1": "gupy", "indeed-1": "indeed"}
    result = dedupe_jobs_tracked([j1, j2], source_by_id)
    assert len(result.jobs) == 1
    winner = result.jobs[0]
    assert winner.id in result.also_sources
    assert set(result.also_sources[winner.id]) == {"gupy", "indeed"} - {source_by_id[winner.id]}


def test_dedupe_different_urls_keeps_both():
    j1 = _job("a", "https://example.com/vaga-a", title="Backend")
    j2 = _job("b", "https://example.com/vaga-b", title="Frontend")
    result = dedupe_jobs_tracked([j1, j2], {"a": "gupy", "b": "indeed"})
    assert len(result.jobs) == 2
    assert not result.also_sources
