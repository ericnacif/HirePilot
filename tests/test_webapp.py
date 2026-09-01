"""Testes da camada web: helpers, SessionStore e endpoints sem rede."""

import io
import sqlite3
import time

from cv_apply.profile import CandidateProfile
from cv_apply.storage import Storage
from cv_apply.webapp import SessionData, SessionStore, _format_posted, app


def _csrf_headers(client):
    client.get("/")
    with client.session_transaction() as sess:
        return {"X-CSRF-Token": sess["csrf_token"]}


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


def test_api_meta():
    client = app.test_client()
    resp = client.get("/api/meta")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["version"]
    assert data["variant"] in ("lite", "full")


def test_index_serve_html():
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"app.js" in resp.data
    assert b'csrf-token' in resp.data
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]


def test_search_sem_perfil_retorna_erro():
    client = app.test_client()
    resp = client.post("/api/search", json={"keywords": "dev"}, headers=_csrf_headers(client))
    assert resp.get_json()["error"]


def test_post_sem_csrf_e_bloqueado():
    client = app.test_client()
    client.get("/")
    resp = client.post("/api/search", json={"keywords": "dev"})
    assert resp.status_code == 403


def test_api_nao_pode_ser_cacheada():
    client = app.test_client()
    resp = client.get("/api/meta")
    assert "no-store" in resp.headers["Cache-Control"]
    assert resp.get_json()["csrf_token"]


def test_perfil_web_e_criptografado_quando_ha_segredo(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_APPLY_SECRET", "s" * 40)
    storage = Storage(tmp_path)
    profile = CandidateProfile(name="Pessoa", email="privado@example.com", raw_text="segredo")
    storage.save_web_profile("sid", profile)
    with sqlite3.connect(storage.db_path) as conn:
        raw = conn.execute("SELECT profile_json FROM web_profiles WHERE sid='sid'").fetchone()[0]
    assert raw.startswith("fernet:")
    assert "privado@example.com" not in raw
    assert storage.load_web_profile("sid") == profile


def test_upload_rejeita_extensao_e_conteudo_falso():
    client = app.test_client()
    headers = _csrf_headers(client)
    bad_ext = client.post(
        "/api/upload", data={"resume": (io.BytesIO(b"x"), "cv.exe")},
        headers=headers, content_type="multipart/form-data",
    )
    assert bad_ext.status_code == 400
    assert "Formato inválido" in bad_ext.get_json()["error"]
    bad_pdf = client.post(
        "/api/upload", data={"resume": (io.BytesIO(b"not a pdf"), "cv.pdf")},
        headers=headers, content_type="multipart/form-data",
    )
    assert bad_pdf.status_code == 400
    assert "PDF ou DOCX válido" in bad_pdf.get_json()["error"]


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
    headers = _csrf_headers(client)
    # estoura o limite global de requisições à API numa única sessão
    statuses = [client.post("/api/search", json={}, headers=headers).status_code for _ in range(40)]
    assert 429 in statuses
