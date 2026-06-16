"""Testes de fontes e hints."""

from cv_apply.filters import SearchFilters
from cv_apply.sources import source_zero_hint


def test_source_zero_hint_remote_requires_filter():
    f = SearchFilters(workplace=["presencial"])
    hint = source_zero_hint("remoteok", f)
    assert hint and "remoto" in hint.lower()
