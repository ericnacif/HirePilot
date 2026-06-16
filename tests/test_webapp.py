"""Testes da camada web: helpers, SessionStore e endpoints sem rede."""

import time

from cv_apply.webapp import SessionData, SessionStore, _format_posted, app


def test_format_posted_iso_e_rotulos():
    assert _format_posted(None) is None
    assert _format_posted("") is None
    assert _format_posted("já legível") == "já legível"


def test_session_store_expira_sessoes():
    store = SessionStore(ttl=0, max_sessions=10)
    s = store.get("abc")
    assert s is not None
    time.sleep(0.01)
    # nova chamada para outra sessão dispara eviction da expirada
    store.get("other")
    assert store.get("abc", create=False) is None


def test_index_serve_html():
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"app.js" in resp.data


def test_search_sem_perfil_retorna_erro():
    client = app.test_client()
    resp = client.post("/api/search", json={"keywords": "dev"})
    assert resp.get_json()["error"]


def test_export_csv_vazio_tem_cabecalho():
    client = app.test_client()
    resp = client.get("/api/export?format=csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert b"score" in resp.data and b"title" in resp.data


def test_export_json_vazio():
    client = app.test_client()
    resp = client.get("/api/export?format=json")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    assert resp.get_json() == []


def test_rate_ok_janela_deslizante():
    sess = SessionData()
    assert sess.rate_ok("b", max_per_window=2, window=60) is True
    assert sess.rate_ok("b", max_per_window=2, window=60) is True
    # terceiro hit dentro da janela estoura o limite
    assert sess.rate_ok("b", max_per_window=2, window=60) is False
    # janela "expirada" (0s) zera a contagem
    assert sess.rate_ok("b", max_per_window=2, window=0) is True


def test_api_404_json_amigavel():
    client = app.test_client()
    resp = client.get("/api/nao-existe")
    assert resp.status_code == 404
    assert resp.get_json()["error"]


def test_rate_limit_global_bloqueia_apos_muitas_chamadas():
    client = app.test_client()
    # estoura o limite global de requisições à API numa única sessão
    statuses = [client.post("/api/search", json={}).status_code for _ in range(40)]
    assert 429 in statuses
