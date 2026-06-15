"""Testes dos extratores do parser de currículo (funções puras de texto)."""

from cv_apply.resume_parser import (
    extract_email,
    extract_name,
    extract_phone,
    extract_seniority,
    extract_skills,
    extract_years_experience,
)


def test_extract_email():
    assert extract_email("Contato: eric.nacif@example.com") == "eric.nacif@example.com"
    assert extract_email("sem email") is None


def test_extract_phone():
    assert extract_phone("Tel: +55 (31) 99999-8888") is not None
    assert extract_phone("nada aqui") is None


def test_extract_name_primeira_linha():
    assert extract_name("Eric Nacif\nDesenvolvedor\n") == "Eric Nacif"
    # linha com número/email não é nome
    assert extract_name("eric@example.com\nEric") is None


def test_extract_skills_inclui_simbolos():
    skills = extract_skills("Experiência com C++ e Python.")
    assert "c++" in skills
    assert "python" in skills


def test_extract_seniority_usa_topo():
    texto = "Eric Nacif\nDesenvolvedor Júnior\n\nExperiência:\nEstágio na empresa X"
    assert extract_seniority(texto) == "júnior"


def test_extract_seniority_none_quando_ausente():
    assert extract_seniority("Eric Nacif\nDesenvolvedor\nProjetos diversos") is None


def test_extract_years_experience():
    assert extract_years_experience("Tenho 5 anos de experiência") == 5
    assert extract_years_experience("3 years of experience") == 3
    assert extract_years_experience("sem números") is None
