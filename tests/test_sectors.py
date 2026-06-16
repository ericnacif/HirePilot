"""Testes do boost de ranqueamento por setor."""

from cv_apply.matching import match_job
from cv_apply.profile import CandidateProfile, JobPosting
from cv_apply.sectors import (
    apply_sector_boost,
    sector_gate_terms,
    sector_query,
    sector_search_queries,
    sector_skills,
)


def _match(title, description, score=None):
    profile = CandidateProfile(skills=["python"])
    job = JobPosting(
        id=title, title=title, company="X", url="u", description=description
    )
    m = match_job(profile, job, use_semantic=False)
    if score is not None:
        m.score = score
    return m


def test_sector_skills_conhecido_e_desconhecido():
    assert "sql" in sector_skills("tec_dados")
    assert sector_skills("inexistente") == []
    assert sector_skills("") == []


def test_sector_query_primario():
    assert sector_query("tec_dev") == "desenvolvedor"
    assert sector_query("tec_all") == "tecnologia"
    assert sector_query("fiscal") == "fiscal"
    assert sector_query("emprego_geral") == "auxiliar administrativo"
    assert sector_query("varejo") == "vendedor"
    assert sector_query("inexistente") == ""


def test_sector_search_queries_multiplas():
    queries = sector_search_queries("tec_all")
    assert len(queries) >= 5
    assert "tecnologia" in queries
    dev = sector_search_queries("tec_dev")
    assert "desenvolvedor" in dev
    assert sector_search_queries("inexistente") == []


def test_sector_gate_terms_inclui_skills_e_termo():
    terms = sector_gate_terms("tec_dev")
    assert "python" in terms and "php" in terms
    # "desenvolvedor" é genérico e não entra como termo de gate
    assert "desenvolvedor" not in terms
    fiscal = sector_gate_terms("fiscal")
    assert "fiscal" in fiscal


def test_boost_aumenta_score_de_vaga_da_area():
    m = _match("Analista", "Vaga com SQL, Python, ETL e Power BI", score=50.0)
    apply_sector_boost([m], "tec_dados")
    assert m.score > 50.0


def test_boost_nao_altera_sem_setor():
    m = _match("Dev", "algo genérico", score=40.0)
    apply_sector_boost([m], "")
    assert m.score == 40.0


def test_boost_reordena_por_score():
    a = _match("Vaga A", "nada relacionado", score=60.0)
    b = _match("Vaga B", "SQL Python ETL Power BI Spark", score=55.0)
    ranked = apply_sector_boost([a, b], "tec_dados")
    # B deve subir acima de A após o boost da área de dados
    assert ranked[0].job.title == "Vaga B"


def test_boost_respeita_teto_de_100():
    m = _match("Dados", "SQL Python ETL Power BI Spark pandas data", score=95.0)
    apply_sector_boost([m], "tec_dados")
    assert m.score <= 100.0
