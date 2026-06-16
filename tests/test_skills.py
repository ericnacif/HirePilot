"""Testes do dicionário de skills e do matcher de tokens (símbolos incluídos)."""

import pytest

from cv_apply.skills_dict import (
    compile_skill_regex,
    find_skills,
    skill_pattern,
    text_has_skill,
)


@pytest.mark.parametrize(
    "skill,text,expected",
    [
        ("c++", "experiência com c++ no projeto", True),
        ("c++", "c++ no fim da frase.", True),
        ("c++", "c+++ algo estranho", False),
        ("c#", "uso de c#, etc", True),
        (".net", "stack .net aqui", True),
        (".net", "trabalho com asp.net mvc", False),
        ("c", "c++ listado", False),  # "c" não casa dentro de "c++"
        ("react", "React. E mais", True),
        ("react", "reactjs framework", False),
        ("node.js", "uso node.js. fim", True),
        ("python", "python, java", True),
    ],
)
def test_skill_boundaries(skill, text, expected):
    assert bool(compile_skill_regex(skill).search(text.lower())) is expected


def test_find_skills_detecta_simbolos():
    skills = find_skills("Sei C++, C#, .NET Core, Node.js, React e Python.")
    assert "c++" in skills
    assert "c#" in skills
    assert ".net" in skills
    assert "python" in skills
    assert "react" in skills


def test_find_skills_ordenado_e_sem_duplicatas():
    skills = find_skills("python PYTHON Python java")
    assert skills.count("python") == 1
    assert skills == sorted(skills, key=str.lower)


def test_skill_pattern_e_string():
    assert isinstance(skill_pattern("python"), str)


def test_compile_skill_regex_usa_cache():
    a = compile_skill_regex("python")
    b = compile_skill_regex("python")
    assert a is b


@pytest.mark.parametrize(
    "text,canonical",
    [
        ("trabalho com JS no front", "javascript"),
        ("clusters em k8s", "kubernetes"),
        ("backend em golang", "go"),
        ("banco postgres aqui", "postgresql"),
        ("app em nextjs", "next.js"),
        ("uso de TS no projeto", "typescript"),
    ],
)
def test_find_skills_reconhece_sinonimos(text, canonical):
    assert canonical in find_skills(text)


def test_find_skills_colapsa_variantes_duplicadas():
    skills = find_skills("golang e go, postgres e postgresql, k8s e kubernetes")
    assert skills.count("go") == 1
    assert "golang" not in skills
    assert skills.count("postgresql") == 1
    assert "postgres" not in skills
    assert skills.count("kubernetes") == 1


def test_text_has_skill_via_sinonimo():
    assert text_has_skill("javascript", "vaga pede js avançado") is True
    assert text_has_skill("kubernetes", "experiência com k8s") is True
    assert text_has_skill("typescript", "somente java aqui") is False
