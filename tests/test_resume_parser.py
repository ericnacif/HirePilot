"""Testes dos extratores do parser de currículo (funções puras de texto)."""

import pytest

from cv_apply.resume_parser import (
    extract_email,
    extract_locations,
    extract_name,
    extract_phone,
    extract_seniority,
    extract_skills,
    extract_years_experience,
    validate_resume_text,
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


def test_extract_locations_nacional_e_internacional():
    locs = extract_locations("Baseado em São Paulo, aberto a vagas em London e Lisbon. Remote ok.")
    assert "São Paulo" in locs
    assert "London" in locs
    assert "Lisbon" in locs
    assert "Remote" in locs


def _sample_resume() -> str:
    return """
Eric Nacif
Desenvolvedor PHP Júnior
eric.nacif@example.com | (31) 99999-8888

Resumo profissional
Desenvolvedor com foco em Laravel e APIs.

Experiência
Empresa X — Desenvolvedor PHP (2022–2024)
Empresa Y — Estágio em TI (2021)

Formação
Bacharelado em Ciência da Computação

Habilidades
PHP, Laravel, MySQL, Git, Docker
"""


def test_validate_resume_text_aceita_curriculo():
    validate_resume_text(_sample_resume())


def test_validate_resume_text_rejeita_vazio():
    with pytest.raises(ValueError, match="extrair texto"):
        validate_resume_text("   ")


def test_validate_resume_text_rejeita_texto_curto():
    with pytest.raises(ValueError, match="insuficiente"):
        validate_resume_text("Eric Nacif\nDesenvolvedor\nemail@test.com")


def test_validate_resume_text_rejeita_nota_fiscal():
    texto = """
NOTA FISCAL ELETRÔNICA NF-e
Chave de acesso: 123456789
Destinatário: Empresa ABC
Emitente: Loja XYZ
Valor total da nota: R$ 150,00
ICMS: R$ 20,00
CFOP: 5102
""" * 3
    with pytest.raises(ValueError, match="não parece ser um currículo"):
        validate_resume_text(texto)


def test_validate_resume_text_rejeita_artigo_generico():
    texto = " ".join(["Este é um artigo sobre economia e política internacional."] * 40)
    with pytest.raises(ValueError, match="não parece ser um currículo"):
        validate_resume_text(texto)


def test_validate_resume_text_rejeita_plano_de_acao():
    texto = """
Relatório de auditoria
Café Sustentável - Ano 3
Propriedade: Fazendinha Teste
Responsável: Seu João

Resumo: 1.11 O produtor deve implementar planos voltados para melhoria continua.
Resposta: Cumpre
Data Limite Adequação:

Plano De Ação:
Percentual alcançado: 20,37%
Nível: Básico
""" * 8
    with pytest.raises(ValueError, match="não parece ser um currículo"):
        validate_resume_text(texto)
