"""Testes da fonte Catho (sem rede)."""

from unittest.mock import MagicMock, patch

from cv_apply.profile import JobPosting
from cv_apply.sources_catho import _parse_card, search_catho


def _mock_article(title="Dev PHP", href="/vagas/dev-php/123", company="Acme", location="SP"):
    art = MagicMock()
    link = MagicMock()
    link.count.return_value = 1
    link.get_attribute.return_value = href
    link.inner_text.return_value = title
    link_wrap = MagicMock()
    link_wrap.first = link
    link_wrap.count.return_value = 1
    art.locator.side_effect = lambda sel: {
        "h2.title_offer a": link_wrap,
        'a[href*="/vagas/"]': link_wrap,
        "p span.text-12": _text_loc(company),
        "p:has(span.i_job_location)": _text_loc(f"1 vaga - {location}"),
    }.get(sel, MagicMock(count=MagicMock(return_value=0)))
    return art


def _text_loc(text):
    loc = MagicMock()
    loc.count.return_value = 1
    loc.inner_text.return_value = text
    wrap = MagicMock()
    wrap.first = loc
    wrap.count.return_value = 1
    return wrap


def test_parse_card_monta_job():
    job = _parse_card(_mock_article())
    assert job is not None
    assert job.title == "Dev PHP"
    assert job.company == "Acme"
    assert job.id.startswith("catho:")
    assert "123" in job.url


def test_search_catho_chama_scraper():
    fake_job = JobPosting(
        id="catho:1",
        title="Dev",
        company="Co",
        url="https://www.catho.com.br/vagas/dev/1",
    )
    mock_page = MagicMock()
    with patch("cv_apply.sources_catho.open_portal_context") as mock_open, patch(
        "cv_apply.sources_catho.close_portal_context"
    ), patch("cv_apply.sources_catho._catho_logged_in", return_value=True), patch(
        "cv_apply.sources_catho._scrape_catho", return_value=[fake_job]
    ):
        mock_open.return_value = (MagicMock(), MagicMock(), mock_page)
        from cv_apply.filters import SearchFilters

        jobs = search_catho(MagicMock(), SearchFilters(keywords="php", broad_mode=True), 5)
    assert len(jobs) == 1
    assert jobs[0].title == "Dev"
