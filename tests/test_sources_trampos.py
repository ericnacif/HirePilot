"""Testes da fonte Trampos.co (sem rede)."""

from unittest.mock import MagicMock, patch

from cv_apply.filters import SearchFilters
from cv_apply.sources_trampos import _item_to_job, search_trampos


def test_item_to_job_monta_campos():
    row = {
        "opportunity": {
            "id": 99,
            "name": "Dev PHP",
            "company_name": "Startup",
            "permalink": "https://trampos.co/oportunidades/99-dev-php",
            "published_at": "2026-06-22 10:00:00 -0300",
        }
    }
    job = _item_to_job(row)
    assert job is not None
    assert job.title == "Dev PHP"
    assert job.company == "Startup"
    assert "trampos.co" in job.url


def test_search_trampos_parseia_resposta():
    payload = [
        {
            "opportunity": {
                "id": 1,
                "name": "Analista",
                "company_name": "Co",
                "permalink": "https://trampos.co/oportunidades/1-analista",
            }
        }
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    filters = SearchFilters(keywords="analista", broad_mode=True)
    with patch("cv_apply.sources_trampos.httpx.Client", return_value=mock_client):
        jobs = search_trampos(MagicMock(), filters, max_jobs=5)
    assert len(jobs) == 1
    assert jobs[0].title == "Analista"
