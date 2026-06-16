"""Testes de extração e filtro salarial."""

from cv_apply.profile import JobPosting
from cv_apply.salary import extract_salary, filter_by_salary


def _job(desc="", title="Dev"):
    return JobPosting(id="1", title=title, company="X", url="u", description=desc)


def test_extract_salary_brl_range():
    j = _job("Faixa: R$ 5.000 a R$ 8.000 mensais")
    lo, hi, text = extract_salary(j)
    assert lo == 5000
    assert hi == 8000
    assert text


def test_filter_by_salary_mantem_sem_salario():
    jobs = [_job("sem salário"), _job("R$ 10.000")]
    out = filter_by_salary(jobs, 8000, None)
    assert len(out) == 2
