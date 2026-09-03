"""Testes da camada web: helpers, SessionStore e endpoints sem rede."""

import io
import sqlite3
import time

import cv_apply.webapp as webapp
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


def test_pwa_shell_e_diagnostico():
    client = app.test_client()
    assert client.get("/static/manifest.json").status_code == 200
    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert sw.headers["Service-Worker-Allowed"] == "/"
    diagnostic = client.get("/api/diagnostics")
    assert diagnostic.status_code == 200
    assert diagnostic.get_json()["ok"] is True


def test_healthcheck_nao_expoe_sessao():
    client = app.test_client()
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.data == b"ok"
    assert "Set-Cookie" not in resp.headers


def test_desktop_autentica_por_bootstrap_sem_token_na_url(monkeypatch):
    monkeypatch.setattr(webapp, "DESKTOP_AUTH_TOKEN", "segredo-desktop")
    monkeypatch.setattr(webapp, "DESKTOP_BOOT_NONCE", "nonce-de-boot")
    client = app.test_client()

    assert client.get("/").status_code == 403
    boot = client.get("/desktop-boot/nonce-de-boot")
    assert boot.status_code == 200
    assert "segredo-desktop" in boot.get_data(as_text=True)
    assert "segredo-desktop" not in boot.request.path
    assert client.get("/desktop-boot/nonce-errado").status_code == 404
    assert client.get("/?desktop_token=segredo-desktop").status_code == 403
    authorized = client.post(
        "/desktop-auth",
        data="segredo-desktop",
        content_type="text/plain",
    )
    assert authorized.status_code == 200
    assert client.get("/").status_code == 200


def test_desktop_rejeita_token_invalido(monkeypatch):
    monkeypatch.setattr(webapp, "DESKTOP_AUTH_TOKEN", "segredo-desktop")
    client = app.test_client()

    response = client.post("/desktop-auth", data="nao-e-o-token", content_type="text/plain")

    assert response.status_code == 403
    assert client.get("/").status_code == 403


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


def test_sse_nao_expoe_detalhes_da_excecao(monkeypatch):
    client = app.test_client()
    headers = _csrf_headers(client)
    with client.session_transaction() as flask_session:
        sid = flask_session["sid"]
    webapp.store.get(sid).profile = CandidateProfile(name="Pessoa")

    def fail(*_args, **_kwargs):
        raise RuntimeError("segredo-interno-nao-deve-vazar")

    monkeypatch.setattr(webapp, "_run_search", fail)
    resp = client.post("/api/search/stream", json={}, headers=headers)

    assert resp.status_code == 200
    assert "no-store" in resp.headers["Cache-Control"]
    assert "segredo-interno-nao-deve-vazar" not in resp.get_data(as_text=True)
    assert "Erro na busca. Tente novamente." in resp.get_data(as_text=True)


def test_sid_invalido_e_regenerado():
    client = app.test_client()
    client.get("/")
    with client.session_transaction() as flask_session:
        flask_session["sid"] = "../../arquivo-sensivel"

    assert client.get("/api/meta").status_code == 200
    with client.session_transaction() as flask_session:
        sid = flask_session["sid"]
    assert len(sid) == 32
    assert all(char in "0123456789abcdef" for char in sid)


def test_payload_com_id_nao_textual_e_rejeitado():
    client = app.test_client()
    resp = client.post(
        "/api/state/favorite",
        json={"id": ["nao", "valido"], "favorite": True},
        headers=_csrf_headers(client),
    )
    assert resp.status_code == 400


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


def test_storage_persiste_versoes_e_exporta_estado(tmp_path):
    storage = Storage(tmp_path)
    profile = CandidateProfile(name="Pessoa", skills=["python"])
    storage.save_resume_version("sid", profile, "curriculo.pdf")
    storage.save_favorite("sid", "job-1", {"id": "job-1", "title": "Dev"})
    storage.save_web_profile("sid", profile)
    exported = storage.export_web_data("sid")
    assert exported["favorites"]["job-1"]["title"] == "Dev"
    assert exported["profile"]["name"] == "Pessoa"
    assert exported["resume_versions"][0]["filename"] == "curriculo.pdf"
    storage.delete_web_data("sid")
    assert storage.export_web_data("sid")["favorites"] == {}


def test_importacao_manual_de_vaga(monkeypatch, tmp_path):
    storage = Storage(tmp_path)
    monkeypatch.setattr(webapp, "_db", lambda: storage)
    client = app.test_client()
    headers = _csrf_headers(client)
    with client.session_transaction() as flask_session:
        sid = flask_session["sid"]
    webapp.store.get(sid).profile = CandidateProfile(skills=["python"])
    response = client.post(
        "/api/job/import",
        json={
            "url": "https://example.com/vaga",
            "title": "Desenvolvedor Python",
            "company": "Acme",
            "description": "Python e Docker",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["job"]["source"] == "manual"
    assert response.get_json()["job"]["missing_skills"] == ["docker"]


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
