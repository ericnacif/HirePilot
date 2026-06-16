"""Testes do módulo de localização."""

from cv_apply.locations import (
    LocationScope,
    filter_jobs_by_location,
    job_matches_location,
    parse_location,
)
from cv_apply.profile import JobPosting


def _job(location: str) -> JobPosting:
    return JobPosting(
        id=location, title="Vaga", company="X", url="u", location=location,
    )


def test_parse_city_with_state():
    filt = parse_location("", scope="city", city="Manhuaçu", state="MG")
    assert filt.scope == LocationScope.CITY
    assert filt.city == "Manhuaçu"
    assert filt.state == "MG"
    assert "Manhuaçu" in filt.indeed_query()


def test_parse_freeform_city():
    filt = parse_location("Manhuaçu, MG")
    assert filt.scope == LocationScope.CITY
    assert filt.city == "Manhuaçu"
    assert filt.state == "MG"


def test_city_filter_keeps_local_jobs():
    filt = parse_location("", scope="city", city="Manhuaçu", state="MG")
    jobs = [
        _job("Manhuaçu, MG"),
        _job("Belo Horizonte, MG"),
        _job("Remoto"),
    ]
    out = filter_jobs_by_location(jobs, filt, fallback=False)
    assert [j.location for j in out] == ["Manhuaçu, MG"]


def test_city_filter_with_remote_option():
    filt = parse_location(
        "", scope="city", city="Manhuaçu", state="MG", include_remote=True,
    )
    jobs = [_job("Manhuaçu, MG"), _job("Remoto")]
    out = filter_jobs_by_location(jobs, filt, fallback=False)
    assert len(out) == 2


def test_state_filter_mg():
    filt = parse_location("", scope="state", state="MG")
    jobs = [_job("Manhuaçu, MG"), _job("Curitiba, PR"), _job("Remoto")]
    out = filter_jobs_by_location(jobs, filt, fallback=False)
    assert len(out) == 1
    assert out[0].location == "Manhuaçu, MG"


def test_brazil_excludes_foreign():
    filt = parse_location("Brasil")
    assert job_matches_location("Berlin, Germany", filt) is False
    assert job_matches_location("São Paulo, SP", filt) is True
    assert job_matches_location("Remoto", filt) is True


def test_remote_scope():
    filt = parse_location("", scope="remote")
    assert job_matches_location("Remoto", filt) is True
    assert job_matches_location("São Paulo, SP", filt) is False


def test_foreign_scope():
    filt = parse_location("", scope="foreign")
    assert job_matches_location("London, UK", filt) is True
    assert job_matches_location("São Paulo, SP", filt) is False
