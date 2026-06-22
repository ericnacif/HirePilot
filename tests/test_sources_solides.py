"""Testes da fonte Sólides (sem rede)."""

from unittest.mock import MagicMock, patch

from cv_apply.filters import SearchFilters
from cv_apply.sources_solides import _item_to_job, _location_label, search_solides


def test_location_label_remoto():
    item = {"city": {"name": "São Paulo"}, "state": {"code": "SP"}, "homeOffice": True}
    assert "Remoto" in _location_label(item)


def test_item_to_job_monta_url_e_descricao():
    item = {
        "id": 42,
        "title": "Desenvolvedor PHP",
        "companyName": "Acme",
        "description": "<p>Laravel</p>",
        "seniority": [{"name": "Pleno"}],
        "city": {"name": "BH"},
        "state": {"code": "MG"},
    }
    job = _item_to_job(item)
    assert job.title == "Desenvolvedor PHP"
    assert job.company == "Acme"
    assert "Pleno" in job.description
    assert "vagas.solides.com.br" in job.url


def test_search_solides_parseia_resposta():
    payload = {
        "data": {
            "data": [
                {
                    "id": 1,
                    "title": "Dev PHP",
                    "companyName": "Co",
                    "description": "PHP Laravel",
                    "city": {"name": "SP"},
                    "state": {"code": "SP"},
                }
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    filters = SearchFilters(keywords="php", broad_mode=True)
    with patch("cv_apply.sources_solides.httpx.Client", return_value=mock_client):
        jobs = search_solides(MagicMock(), filters, max_jobs=5)
    assert len(jobs) == 1
    assert jobs[0].title == "Dev PHP"
