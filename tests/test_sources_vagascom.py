"""Testes da fonte Vagas.com (sem rede)."""

from unittest.mock import MagicMock, patch

from cv_apply.profile import JobPosting
from cv_apply.sources_vagascom import _parse_vaga_link, _vagascom_logged_in, search_vagascom


def test_vagascom_logged_in_detecta_vaga_links():
    page = MagicMock()
    page.url = "https://www.vagas.com.br/vagas-de-emprego/dev"
    page.locator.side_effect = lambda sel: {
        'input[name="login_candidatos_form[usuario]"]': MagicMock(count=MagicMock(return_value=0)),
        'a[href*="/vaga/"]': MagicMock(count=MagicMock(return_value=3)),
        'a[href*="logout"], a[href*="sair"]': MagicMock(count=MagicMock(return_value=0)),
    }.get(sel, MagicMock(count=MagicMock(return_value=0)))
    page.inner_text.return_value = ""
    assert _vagascom_logged_in(page) is True


def test_parse_vaga_link_monta_job():
    link = MagicMock()
    link.get_attribute.side_effect = lambda attr: {
        "href": "/vaga/v123-dev-php",
        "title": "Dev PHP",
    }.get(attr)
    link.inner_text.return_value = "Dev PHP"
    link.locator.return_value.count.return_value = 0
    job = _parse_vaga_link(link)
    assert job is not None
    assert job.title == "Dev PHP"
    assert job.id.startswith("vagascom:")
    assert "v123-dev-php" in job.url


def test_search_vagascom_sem_login_retorna_vazio():
    mock_page = MagicMock()
    with patch("cv_apply.sources_vagascom.open_portal_context") as mock_open, patch(
        "cv_apply.sources_vagascom.close_portal_context"
    ), patch("cv_apply.sources_vagascom.wait_for_portal_login", return_value=False):
        mock_open.return_value = (MagicMock(), MagicMock(), mock_page)
        from cv_apply.filters import SearchFilters

        jobs = search_vagascom(
            MagicMock(), SearchFilters(keywords="php", broad_mode=True), 5
        )
    assert jobs == []


def test_search_vagascom_com_login():
    fake_job = JobPosting(
        id="vagascom:1",
        title="Dev",
        company="Co",
        url="https://www.vagas.com.br/vaga/v1",
    )
    mock_page = MagicMock()
    with patch("cv_apply.sources_vagascom.open_portal_context") as mock_open, patch(
        "cv_apply.sources_vagascom.close_portal_context"
    ), patch("cv_apply.sources_vagascom.wait_for_portal_login", return_value=True), patch(
        "cv_apply.sources_vagascom._scrape_vagascom", return_value=[fake_job]
    ):
        mock_open.return_value = (MagicMock(), MagicMock(), mock_page)
        from cv_apply.filters import SearchFilters

        jobs = search_vagascom(
            MagicMock(), SearchFilters(keywords="php", broad_mode=True), 5
        )
    assert len(jobs) == 1
