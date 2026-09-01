"""Testes dos limites de segurança do aplicativo desktop."""

import pytest

from cv_apply import desktop


def test_open_external_aceita_apenas_http_https(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: opened.append(url) or True)

    assert desktop._DesktopApi.open_external("https://example.com/vaga") is True
    assert desktop._DesktopApi.open_external("http://example.com/vaga") is True
    assert desktop._DesktopApi.open_external("file:///C:/segredo.txt") is False
    assert desktop._DesktopApi.open_external("javascript:alert(1)") is False
    assert opened == ["https://example.com/vaga", "http://example.com/vaga"]


def test_pick_port_falha_quando_intervalo_esta_indisponivel(monkeypatch):
    class BusySocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def setsockopt(self, *_args):
            return None

        def bind(self, *_args):
            raise OSError("ocupada")

    monkeypatch.setattr(desktop.socket, "socket", lambda *_args: BusySocket())
    with pytest.raises(OSError, match="Nenhuma porta local disponível"):
        desktop._pick_port(59000, 59002)
