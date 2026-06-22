"""Testes dos filtros de senioridade e relevância pós-busca."""

from cv_apply.profile import JobPosting
from cv_apply.relevance import (
    detect_seniority_levels,
    extract_query_terms,
    filter_by_experience,
    filter_by_location,
    filter_by_relevance,
    resolve_wanted_experience,
    seniority_mismatch_penalty,
)


def _job(title, description="", location=""):
    return JobPosting(
        id=title, title=title, company="X", url="u",
        description=description, location=location,
    )


def test_detect_seniority_levels():
    assert detect_seniority_levels("Desenvolvedor Júnior") == {"junior"}
    assert detect_seniority_levels("Desenvolvedor Sênior") == {"senior"}
    assert "senior" in detect_seniority_levels("Senior Software Engineer")
    assert detect_seniority_levels("Desenvolvedor Full Stack") == set()


def test_detect_nao_casa_dentro_de_palavra():
    # "sr" não deve casar dentro de "amostra"
    assert "senior" not in detect_seniority_levels("Analista de amostra")


def test_filter_by_experience_remove_senior_quando_pede_junior():
    jobs = [
        _job("Desenvolvedor Júnior"),
        _job("Desenvolvedor Sênior"),
        _job("Desenvolvedor Full Stack"),  # ambíguo, mantém
    ]
    out = filter_by_experience(jobs, ["junior"])
    titles = [j.title for j in out]
    assert "Desenvolvedor Júnior" in titles
    assert "Desenvolvedor Full Stack" in titles
    assert "Desenvolvedor Sênior" not in titles


def test_filter_by_experience_sem_filtro_mantem_tudo():
    jobs = [_job("Dev Sênior"), _job("Dev Júnior")]
    assert filter_by_experience(jobs, []) == jobs
    # nível desconhecido (não mapeado) também não filtra
    assert filter_by_experience(jobs, ["diretor"]) == jobs


def test_extract_query_terms_ignora_genericos():
    assert extract_query_terms("desenvolvedor php") == ["php"]
    assert extract_query_terms("desenvolvedor full stack") == []
    assert set(extract_query_terms("php, laravel")) == {"php", "laravel"}


def test_filter_by_relevance_mantem_so_php():
    jobs = [
        _job("Desenvolvedor PHP", "Laravel e MySQL"),
        _job("Desenvolvedor Python", "Django e FastAPI"),
        _job("Desenvolvedor Java", "Spring Boot"),
    ]
    out = filter_by_relevance(jobs, ["php"])
    assert len(out) == 1
    assert out[0].title == "Desenvolvedor PHP"


def test_filter_by_relevance_fallback_quando_nada_bate():
    jobs = [_job("Desenvolvedor Python"), _job("Desenvolvedor Java")]
    # nenhum tem "cobol" → devolve a lista original em vez de zerar
    assert filter_by_relevance(jobs, ["cobol"]) == jobs


def test_filter_by_relevance_sem_termos():
    jobs = [_job("Qualquer")]
    assert filter_by_relevance(jobs, []) == jobs


def test_filter_by_relevance_sem_fallback_pode_zerar():
    jobs = [_job("Desenvolvedor Python"), _job("Desenvolvedor Java")]
    assert filter_by_relevance(jobs, ["cobol"], fallback=False) == []


def test_filter_by_location_brasil_mantem_remoto_e_br():
    jobs = [
        _job("Dev", "", "Remoto"),
        _job("Dev", "", "São Paulo, SP"),
        _job("Dev", "", "Berlin, Germany"),
    ]
    out = filter_by_location(jobs, "Brasil")
    locs = [j.location for j in out]
    assert "Remoto" in locs
    assert "São Paulo, SP" in locs
    assert "Berlin, Germany" not in locs


def test_filter_by_location_fallback_quando_nada_bate():
    jobs = [_job("Dev", "", "Tokyo, Japan")]
    assert filter_by_location(jobs, "Brasil") == jobs


def test_resolve_wanted_experience_prefere_chips():
    assert resolve_wanted_experience(["junior"], "sênior") == ["junior"]


def test_resolve_wanted_experience_fallback_perfil():
    assert resolve_wanted_experience([], "júnior") == ["junior"]
    assert resolve_wanted_experience(None, "pleno") == ["pleno"]


def test_resolve_wanted_experience_vazio():
    assert resolve_wanted_experience([], None) == []


def test_seniority_mismatch_penalty():
    job = _job("Desenvolvedor Sênior")
    assert seniority_mismatch_penalty(["junior"], job) == 25.0
    assert seniority_mismatch_penalty(["junior"], _job("Desenvolvedor Júnior")) == 0.0
    assert seniority_mismatch_penalty([], job) == 0.0
