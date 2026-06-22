"""Testes do health check por fonte."""

from unittest.mock import MagicMock, patch

from cv_apply.source_health import (
    _entry,
    check_all_sources_health,
    check_gupy_health,
    check_linkedin_health,
    check_solides_health,
    health_summary,
)


def test_health_entry_shape():
    item = _entry("gupy", "ok", "teste", latency_ms=42)
    assert item["source"] == "gupy"
    assert item["status"] == "ok"
    assert item["latency_ms"] == 42


def test_check_gupy_health_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    with patch("cv_apply.source_health.httpx.Client", return_value=mock_client):
        item = check_gupy_health()
    assert item["status"] == "ok"


def test_check_gupy_health_down():
    with patch("cv_apply.source_health._timed_get", side_effect=TimeoutError("timeout")):
        item = check_gupy_health()
    assert item["status"] == "down"


def test_check_solides_health_ok():
    with patch("cv_apply.source_health._timed_get", return_value=(200, 88)):
        item = check_solides_health()
    assert item["status"] == "ok"
    assert item["source"] == "solides"


def test_linkedin_unavailable_without_playwright():
    with patch("cv_apply.source_health._playwright_ready", return_value=(False, "sem playwright")):
        item = check_linkedin_health(MagicMock(browser_data_dir=MagicMock()))
    assert item["status"] == "unavailable"


def test_health_summary():
    items = [
        _entry("gupy", "ok", ""),
        _entry("indeed", "degraded", ""),
        _entry("linkedin", "needs_login", ""),
    ]
    assert health_summary(items) == {"ok": 1, "degraded": 1, "needs_login": 1}


def test_check_all_sources_uses_cache():
    with patch("cv_apply.source_health.check_source_health") as mock_check:
        mock_check.return_value = _entry("gupy", "ok", "cached")
        from cv_apply import source_health

        source_health._HEALTH_CACHE["at"] = 0
        source_health._HEALTH_CACHE["sources"] = []
        check_all_sources_health(force=True)
        first_calls = mock_check.call_count
        check_all_sources_health(force=False)
        assert mock_check.call_count == first_calls
