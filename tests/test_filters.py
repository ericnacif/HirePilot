"""Testes do mapeamento de filtros por plataforma."""

from datetime import datetime, timedelta, timezone

from cv_apply.filters import SearchFilters


def test_linkedin_params_mapeia_filtros():
    f = SearchFilters(
        keywords="dev",
        workplace=["remoto", "hibrido"],
        job_type=["efetivo"],
        experience=["junior"],
        date_posted="semana",
    )
    params = f.linkedin_params()
    assert params["f_WT"] == "2,3"
    assert params["f_JT"] == "F"
    assert params["f_E"] == "2"
    assert params["f_TPR"] == "r604800"


def test_linkedin_params_vazio_quando_sem_filtros():
    assert SearchFilters(keywords="dev").linkedin_params() == {}


def test_gupy_mappings():
    f = SearchFilters(workplace=["remoto"], job_type=["estagio"])
    assert f.gupy_workplace_types() == ["remote"]
    assert f.gupy_job_types() == ["vacancy_type_internship"]


def test_only_remote_e_allows_remote():
    assert SearchFilters(workplace=["remoto"]).only_remote() is True
    assert SearchFilters(workplace=["remoto", "hibrido"]).only_remote() is False
    assert SearchFilters().allows_remote() is True
    assert SearchFilters(workplace=["presencial"]).allows_remote() is False


def test_matches_date_respeita_cutoff():
    f = SearchFilters(date_posted="24h")
    recente = datetime.now(timezone.utc) - timedelta(hours=2)
    antigo = datetime.now(timezone.utc) - timedelta(days=3)
    assert f.matches_date(recente) is True
    assert f.matches_date(antigo) is False


def test_matches_date_sem_filtro_aceita_tudo():
    f = SearchFilters(date_posted="qualquer")
    assert f.matches_date(None) is True
    assert f.matches_date(datetime(2000, 1, 1, tzinfo=timezone.utc)) is True


def test_matches_generic_job_type():
    f = SearchFilters(job_type=["efetivo"])
    assert f.matches_generic_job_type("full_time") is True
    assert f.matches_generic_job_type("internship") is False
    assert SearchFilters().matches_generic_job_type("anything") is True
