"""Testes utilitários de fontes de vagas (sem rede)."""

from datetime import datetime, timezone

from cv_apply.profile import JobPosting
from cv_apply.sources import (
    _gupy_keyword_candidates,
    _make_id,
    _parse_date,
    _strip_html,
    dedupe_jobs,
)


def test_gupy_keyword_candidates_encurta_frase_longa():
    cands = _gupy_keyword_candidates("desenvolvedor programador software full stack")
    assert cands[0] == "desenvolvedor programador software full stack"
    assert cands[-1] == "desenvolvedor"  # cai para o cargo principal
    assert "desenvolvedor programador" in cands


def test_gupy_keyword_candidates_uma_palavra():
    assert _gupy_keyword_candidates("desenvolvedor") == ["desenvolvedor"]


def test_gupy_keyword_candidates_vazio():
    assert _gupy_keyword_candidates("") == [""]


def test_keyword_candidates_alias_e_compartilhado():
    from cv_apply.sources import _keyword_candidates

    assert _keyword_candidates is _gupy_keyword_candidates
    assert _keyword_candidates("a b c d") == ["a b c d", "a b", "a"]


def test_strip_html():
    assert _strip_html("<p>Olá <b>mundo</b></p>") == "Olá mundo"
    assert _strip_html("") == ""


def test_parse_date_timestamp():
    dt = _parse_date(1_718_000_000)
    assert dt is not None
    assert dt.tzinfo is timezone.utc


def test_parse_date_iso():
    dt = _parse_date("2026-06-11T14:07:01")
    assert dt == datetime(2026, 6, 11, 14, 7, 1)


def test_parse_date_invalido():
    assert _parse_date(None) is None
    assert _parse_date("texto qualquer") is None


def test_make_id_curto_e_hash_para_longo():
    assert _make_id("gupy", "123") == "gupy:123"
    longo = "x" * 100
    gerado = _make_id("gupy", longo)
    assert gerado.startswith("gupy:")
    assert len(gerado) < len(f"gupy:{longo}")


def _job(jid, title, company, easy=False, desc=""):
    return JobPosting(id=jid, title=title, company=company, url="http://x",
                      easy_apply=easy, description=desc)


def test_dedupe_remove_duplicatas_mantendo_melhor():
    jobs = [
        _job("1", "Dev Python Júnior", "Acme", easy=False, desc="curta"),
        _job("2", "Dev Python Senior", "Acme", easy=True, desc="descrição bem mais longa aqui"),
    ]
    result = dedupe_jobs(jobs)
    assert len(result) == 1
    assert result[0].id == "2"  # easy apply + descrição maior vence


def test_dedupe_mantem_vagas_distintas():
    jobs = [
        _job("1", "Dev Python", "Acme"),
        _job("2", "Designer", "Outra"),
    ]
    assert len(dedupe_jobs(jobs)) == 2
