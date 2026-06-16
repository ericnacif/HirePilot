"""Testes do cache de busca."""

from cv_apply.config import Settings
from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting
from cv_apply.search_cache import SearchCache


def test_cache_hit_miss():
    cache = SearchCache(ttl_seconds=60)
    settings = Settings(search_keywords="php", search_sources=["gupy"])
    filters = SearchFilters.from_settings(settings)
    key = cache.make_key("gupy", settings, filters, 20)
    assert cache.get(key) is None
    jobs = [JobPosting(id="gupy:1", title="Dev PHP", company="A", url="http://x")]
    cache.set(key, jobs)
    hit = cache.get(key)
    assert hit and hit[0].title == "Dev PHP"
