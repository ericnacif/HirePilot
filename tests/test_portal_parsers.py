"""Testes de parsers HTML de portais (fixtures leves, sem rede)."""

from cv_apply.sources_empregoscom import _parse_html


EMPREGOS_FIXTURE = """
<html><body>
<a href="/vagas-desenvolvedor-python">Desenvolvedor Python</a>
<a href="/empregos-analista-dados">Analista de Dados</a>
<a href="/static/style.css">ignore</a>
</body></html>
"""


def test_empregoscom_parse_html():
    jobs = _parse_html(EMPREGOS_FIXTURE, cap=10)
    titles = {j.title for j in jobs}
    assert "Desenvolvedor Python" in titles
    assert "Analista de Dados" in titles
    assert all(j.url.startswith("https://www.empregos.com.br") for j in jobs)
    assert all(j.id.startswith("empregoscom:") for j in jobs)
