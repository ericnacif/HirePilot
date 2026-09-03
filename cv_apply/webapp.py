"""Micro-interface web reutilizável: cada pessoa sobe o currículo, recebe a
nota ATS e busca/ranqueia/aplica em vagas. Estado isolado por sessão.

O front-end fica em ``templates/index.html`` + ``static/`` (CSS e JS).
O estado por sessão é guardado em memória com expiração automática
(:class:`SessionStore`) para não crescer indefinidamente.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import queue
import re
import secrets
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from cv_apply.ats import analyze_ats, analyze_resume_format
from cv_apply.config import get_settings
from cv_apply.cover_letter import generate_cover_letter
from cv_apply.profile import CandidateProfile, JobPosting
from cv_apply.resume_parser import parse_resume
from cv_apply.salary import extract_salary
from cv_apply.search_pipeline import apply_payload_to_settings, execute_search, job_row
from cv_apply.sources import AVAILABLE_SOURCES
from cv_apply.storage import Storage
from cv_apply.tailor import tailor_resume_markdown

logger = logging.getLogger(__name__)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))
MAX_JSON_BYTES = int(os.getenv("MAX_JSON_KB", "64")) * 1024
WEB_PRODUCTION = os.getenv("WEB_PRODUCTION", "false").lower() in {"1", "true", "yes"}
WEB_ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("WEB_ALLOWED_HOSTS", "").split(",") if host.strip()
]
DESKTOP_AUTH_TOKEN = os.getenv("DESKTOP_AUTH_TOKEN", "")
DESKTOP_BOOT_NONCE = os.getenv("DESKTOP_BOOT_NONCE", "")
SESSION_TTL_SECONDS = 2 * 60 * 60  # 2h sem uso → expira


def _resource_dir(name: str) -> str:
    """Caminho de ``templates``/``static`` rodando do código ou empacotado.

    No executável do PyInstaller os dados são extraídos em ``sys._MEIPASS``;
    fora dele ficam ao lado deste módulo.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "cv_apply", name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


app = Flask(
    __name__,
    template_folder=_resource_dir("templates"),
    static_folder=_resource_dir("static"),
)
_configured_secret = os.environ.get("CV_APPLY_SECRET", "")
if WEB_PRODUCTION and len(_configured_secret) < 32:
    raise RuntimeError("CV_APPLY_SECRET deve ter pelo menos 32 caracteres em produção.")
if WEB_PRODUCTION and not WEB_ALLOWED_HOSTS:
    raise RuntimeError("WEB_ALLOWED_HOSTS deve listar os hosts públicos em produção.")
app.secret_key = _configured_secret or os.urandom(32).hex()
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=WEB_PRODUCTION,
    SESSION_COOKIE_NAME="__Host-vagaemvista" if WEB_PRODUCTION else "vagaemvista_session",
    PERMANENT_SESSION_LIFETIME=SESSION_TTL_SECONDS,
    TRUSTED_HOSTS=WEB_ALLOWED_HOSTS or None,
)
if os.getenv("TRUST_PROXY", "false").lower() in {"1", "true", "yes"}:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

ALLOWED_EXT = {".pdf", ".docx"}
VALID_SENIORITY = {"estagiário", "júnior", "pleno", "sênior"}
UPLOAD_RETENTION_SECONDS = int(os.getenv("UPLOAD_RETENTION_HOURS", "2")) * 60 * 60
# Rate limit simples: janela deslizante por sessão
RATE_LIMIT_WINDOW = 60  # segundos
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "30"))  # requisições/janela
SEARCH_RATE_MAX = int(os.getenv("SEARCH_RATE_MAX", "8"))  # buscas/janela
MAX_SESSIONS = 200
_alert_hits: list[dict] = []
_ip_hits: dict[str, list[float]] = {}
_ip_hits_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Estado por sessão (em memória, com expiração)                               #
# --------------------------------------------------------------------------- #
@dataclass
class SessionData:
    profile: CandidateProfile | None = None
    resume_path: Path | None = None
    jobs: dict[str, JobPosting] = field(default_factory=dict)
    source_by_job: dict[str, str] = field(default_factory=dict)
    applied: set[str] = field(default_factory=set)
    last_results: list[dict] = field(default_factory=list)
    hits: dict[str, list[float]] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)

    def rate_ok(self, bucket: str, max_per_window: int, window: float) -> bool:
        """Janela deslizante: registra o hit e diz se está dentro do limite."""
        now = time.time()
        recent = [t for t in self.hits.get(bucket, []) if now - t < window]
        recent.append(now)
        self.hits[bucket] = recent
        return len(recent) <= max_per_window


def _delete_resume_file(path: Path | None) -> None:
    """Remove um upload temporário, ignorando erros não críticos."""
    if not path:
        return
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        logger.warning("Não foi possível remover upload antigo: %s", path)


class SessionStore:
    """Guarda o estado por sessão e descarta sessões antigas."""

    def __init__(self, ttl: int = SESSION_TTL_SECONDS, max_sessions: int = MAX_SESSIONS):
        self._data: dict[str, SessionData] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max = max_sessions

    def _evict_locked(self) -> None:
        now = time.time()
        expired = [k for k, v in self._data.items() if now - v.last_seen > self._ttl]
        for k in expired:
            entry = self._data.pop(k, None)
            if entry:
                _delete_resume_file(entry.resume_path)
        if len(self._data) > self._max:
            ordered = sorted(self._data.items(), key=lambda kv: kv[1].last_seen)
            for k, _ in ordered[: len(self._data) - self._max]:
                entry = self._data.pop(k, None)
                if entry:
                    _delete_resume_file(entry.resume_path)

    def get(self, sid: str, create: bool = True) -> SessionData | None:
        with self._lock:
            self._evict_locked()
            entry = self._data.get(sid)
            if entry is None and create:
                entry = SessionData()
                self._data[sid] = entry
            if entry is not None:
                entry.last_seen = time.time()
            return entry

    def delete(self, sid: str) -> SessionData | None:
        with self._lock:
            return self._data.pop(sid, None)


store = SessionStore()


def _db() -> Storage:
    return Storage(get_settings().data_dir)


def _suggest_keywords(profile: CandidateProfile) -> str:
    if profile.skills:
        return ", ".join(profile.skills[:3])
    if profile.job_titles:
        return profile.job_titles[0]
    return ""


def _warmup_semantic() -> None:
    settings = get_settings()
    if not settings.use_semantic_matching:
        return

    def _load() -> None:
        try:
            from cv_apply.matching import _get_semantic_model

            _get_semantic_model()
            logger.info("Modelo semântico pré-carregado.")
        except Exception as exc:
            logger.warning("Warm-up semântico falhou: %s", exc)

    threading.Thread(target=_load, name="semantic-warmup", daemon=True).start()


def _run_search(
    sess: SessionData,
    data: dict,
    sid: str,
    *,
    on_source_done=None,
    on_partial=None,
) -> dict:
    """Executa busca e devolve payload JSON."""
    settings = get_settings()
    db = _db()
    seen = db.get_seen_ids(sid)
    ctx = apply_payload_to_settings(data, settings)
    ctx.seen_job_ids = seen
    if data.get("only_new"):
        ctx.only_new = True

    sources = [s.lower() for s in data.get("sources", []) if s.lower() in AVAILABLE_SOURCES]
    settings.search_sources = sources or ["gupy"]

    applied_ids = set(sess.applied) | set(db.get_web_state(sid)["applied"].keys())

    result = execute_search(
        sess.profile,
        settings,
        ctx,
        applied_ids=applied_ids,
        format_posted=_format_posted,
        on_source_done=on_source_done,
        on_partial=on_partial,
        use_cache=not data.get("no_cache"),
    )

    sess.jobs = result.job_models
    sess.source_by_job = result.source_by_id
    sess.last_results = result.jobs
    if result.all_seen_ids:
        db.mark_seen_jobs(sid, result.all_seen_ids)
    if result.job_models:
        db.save_jobs(list(result.job_models.values()))

    return {
        "jobs": result.jobs,
        "sources": result.sources_status,
        "meta": result.meta,
    }


def _cleanup_stale_uploads(upload_dir: Path, retention_seconds: int = UPLOAD_RETENTION_SECONDS) -> None:
    """Remove arquivos de upload antigos deixados por execuções anteriores."""
    if not upload_dir.exists():
        return
    cutoff = time.time() - retention_seconds
    for path in upload_dir.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            logger.warning("Não foi possível limpar upload órfão: %s", path)


def _sid() -> str:
    sid = session.get("sid")
    if not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{32}", sid):
        sid = uuid.uuid4().hex
        session["sid"] = sid
    return sid


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _json_object() -> dict:
    """Retorna apenas payloads JSON-objeto, evitando 500 com listas/escalares."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _job_id(data: dict) -> str | None:
    value = data.get("id")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if 1 <= len(value) <= 256 else None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _request_ip() -> str:
    """Usa o endereço do socket; proxy só é confiado quando configurado."""
    if os.getenv("TRUST_PROXY", "false").lower() in {"1", "true", "yes"}:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded[:64]
    return (request.remote_addr or "unknown")[:64]


def _ip_rate_ok(max_per_window: int = 120, window: int = RATE_LIMIT_WINDOW) -> bool:
    now = time.time()
    key = _request_ip()
    with _ip_hits_lock:
        recent = [t for t in _ip_hits.get(key, []) if now - t < window]
        recent.append(now)
        _ip_hits[key] = recent
        if len(_ip_hits) > 2000:
            stale = [ip for ip, hits in _ip_hits.items() if not hits or now - hits[-1] >= window]
            for ip in stale[:1000]:
                _ip_hits.pop(ip, None)
        return len(recent) <= max_per_window


def _valid_resume_file(path: Path, ext: str) -> bool:
    """Valida assinatura e estrutura antes de entregar o arquivo ao parser."""
    if ext == ".pdf":
        with path.open("rb") as fh:
            return fh.read(5) == b"%PDF-"
    if ext == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                    return False
                entries = archive.infolist()
                total = sum(info.file_size for info in entries)
                return len(entries) <= 1000 and total <= 50 * 1024 * 1024
        except (OSError, zipfile.BadZipFile):
            return False
    return False


def _format_posted(value: str | None) -> str | None:
    """Converte data de publicação em rótulo amigável (ex.: 'há 4 dias')."""
    if not value:
        return None
    raw = value.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:30]  # já é um rótulo legível vindo da fonte
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    days = (now - dt).days
    if days <= 0:
        return "hoje"
    if days == 1:
        return "ontem"
    if days < 30:
        return f"há {days} dias"
    months = days // 30
    return f"há {months} {'mês' if months == 1 else 'meses'}"


def _profile_summary(profile: CandidateProfile, resume_path: Path | None) -> dict:
    checks: list[dict] = []
    format_score = None
    if resume_path and resume_path.exists():
        fc = analyze_resume_format(resume_path, profile.raw_text, profile)
        passed = sum(1 for c in fc if c.passed)
        format_score = round(passed / len(fc) * 100) if fc else None
        checks = [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in fc]
    return {
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "seniority": profile.seniority,
        "years_experience": profile.years_experience,
        "skills": profile.skills,
        "locations": profile.locations,
        "format_score": format_score,
        "format_checks": checks,
    }


def require_profile(fn: Callable) -> Callable:
    """Injeta a sessão atual; erro padrão se o currículo ainda não foi enviado."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        sid = _sid()
        sess = store.get(sid)
        if sess and not sess.profile:
            sess.profile = _db().load_web_profile(sid)
        if not sess or not sess.profile:
            return jsonify({"error": "Envie seu currículo primeiro."})
        return fn(sess, *args, **kwargs)

    return wrapper


def require_job(fn: Callable) -> Callable:
    """Como :func:`require_profile`, mas também resolve a vaga pelo ``id``."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        sid = _sid()
        sess = store.get(sid)
        if sess and not sess.profile:
            sess.profile = _db().load_web_profile(sid)
        if not sess or not sess.profile:
            return jsonify({"error": "Envie seu currículo primeiro."})
        data = _json_object()
        job_id = _job_id(data)
        job = sess.jobs.get(job_id) if job_id else None
        if not job:
            return jsonify({"error": "Sessão expirada — refaça a busca."})
        return fn(sess, job, data, *args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------- #
# Erros e rate limiting                                                         #
# --------------------------------------------------------------------------- #
@app.errorhandler(413)
def _too_large(_err):
    return jsonify({"error": f"Arquivo muito grande. Limite de {MAX_UPLOAD_MB} MB."}), 413


@app.errorhandler(404)
def _not_found(_err):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Recurso não encontrado."}), 404
    return jsonify({"error": "Página não encontrada."}), 404


@app.errorhandler(500)
def _server_error(_err):
    logger.exception("Erro interno")
    return jsonify({"error": "Erro interno. Tente novamente."}), 500


@app.before_request
def _global_rate_limit():
    """Limita a taxa global de chamadas à API por sessão."""
    if request.path == "/healthz":
        return None
    if DESKTOP_AUTH_TOKEN and (
        request.path == "/desktop-auth" or request.path.startswith("/desktop-boot/")
    ):
        if not _ip_rate_ok(int(os.getenv("IP_RATE_LIMIT_MAX", "120"))):
            return jsonify({"error": "Muitas requisições deste endereço. Aguarde."}), 429
        return None
    if DESKTOP_AUTH_TOKEN:
        if not session.get("desktop_authorized"):
            return jsonify({"error": "Acesso local não autorizado."}), 403
    if not request.path.startswith("/api/"):
        return None
    if not _ip_rate_ok(int(os.getenv("IP_RATE_LIMIT_MAX", "120"))):
        return jsonify({"error": "Muitas requisições deste endereço. Aguarde."}), 429
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        fetch_site = request.headers.get("Sec-Fetch-Site", "")
        if fetch_site == "cross-site":
            return jsonify({"error": "Origem da requisição não permitida."}), 403
        provided = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not isinstance(provided, str) or not isinstance(expected, str):
            return jsonify({"error": "Token de segurança inválido. Recarregue a página."}), 403
        if not expected or not secrets.compare_digest(provided, expected):
            return jsonify({"error": "Token de segurança inválido. Recarregue a página."}), 403
        if request.mimetype == "application/json" and (request.content_length or 0) > MAX_JSON_BYTES:
            return jsonify({"error": "Requisição JSON muito grande."}), 413
    sess = store.get(_sid())
    if not sess.rate_ok("api", RATE_LIMIT_MAX, RATE_LIMIT_WINDOW):
        return jsonify({"error": "Muitas requisições. Aguarde um instante."}), 429
    return None


@app.after_request
def _security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self' https://api.github.com"
    )
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
    if WEB_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# --------------------------------------------------------------------------- #
# Rotas                                                                        #
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    _sid()
    return render_template("index.html", csrf_token=_csrf_token())


@app.route("/sw.js")
def service_worker():
    response = app.send_static_file("sw.js")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


def _desktop_boot_html(app_url: str) -> str:
    """Página intermediária que autentica o desktop sem pôr o segredo na URL."""
    app_url_json = json.dumps(app_url, ensure_ascii=False)
    token_json = json.dumps(DESKTOP_AUTH_TOKEN, ensure_ascii=False)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><title>Vaga em Vista</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#101828;color:#F7F8F3;font:16px system-ui,sans-serif}}main{{text-align:center;padding:24px}}p{{color:#AAB4C5}}.dot{{display:inline-block;width:10px;height:10px;margin:0 4px;border-radius:50%;background:#B7F34A;animation:p 1s infinite alternate}}.dot:nth-child(2){{animation-delay:.2s}}.dot:nth-child(3){{animation-delay:.4s}}@keyframes p{{to{{opacity:.25;transform:translateY(-4px)}}}}</style>
</head><body><main><h1>Vaga em Vista</h1><p id="status">Iniciando <span class="dot"></span><span class="dot"></span><span class="dot"></span></p></main>
<script>
(() => {{
  const appUrl = {app_url_json};
  const token = {token_json};
  const status = document.getElementById("status");
  fetch("/desktop-auth", {{method: "POST", body: token, headers: {{"Content-Type": "text/plain"}}}})
    .then((response) => {{
      if (!response.ok) throw new Error("auth");
      window.location.replace(appUrl);
    }})
    .catch(() => {{ status.textContent = "Não foi possível iniciar o aplicativo. Feche e tente novamente."; }});
}})();
</script></body></html>"""


@app.route("/desktop-boot/<nonce>", methods=["GET"])
def desktop_boot(nonce: str):
    if (
        not DESKTOP_AUTH_TOKEN
        or not DESKTOP_BOOT_NONCE
        or not isinstance(nonce, str)
        or not secrets.compare_digest(nonce, DESKTOP_BOOT_NONCE)
    ):
        return jsonify({"error": "Recurso não encontrado."}), 404
    response = Response(_desktop_boot_html(request.url_root), mimetype="text/html")
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/desktop-auth", methods=["POST"])
def desktop_auth():
    if not DESKTOP_AUTH_TOKEN:
        return jsonify({"error": "Autenticação local não configurada."}), 404
    if request.content_length and request.content_length > 512:
        return jsonify({"error": "Token inválido."}), 403
    supplied = request.get_data(cache=True, as_text=True).strip()
    if not supplied or not secrets.compare_digest(supplied, DESKTOP_AUTH_TOKEN):
        return jsonify({"error": "Token inválido."}), 403
    session.clear()
    session["desktop_authorized"] = True
    _sid()
    _csrf_token()
    return jsonify({"ok": True})


@app.route("/healthz")
def healthz():
    return Response("ok", mimetype="text/plain")


@app.route("/api/upload", methods=["POST"])
def api_upload():
    sid = _sid()
    file = request.files.get("resume")
    if not file or not file.filename:
        return jsonify({"error": "Nenhum arquivo enviado."}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "Formato inválido. Envie PDF ou DOCX."}), 400

    settings = get_settings()
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_uploads(upload_dir)
    dest = upload_dir / f"{sid}_{uuid.uuid4().hex}{ext}"
    file.save(str(dest))
    try:
        dest.chmod(0o600)
    except OSError:
        pass

    if not _valid_resume_file(dest, ext):
        _delete_resume_file(dest)
        return jsonify({"error": "O conteúdo do arquivo não corresponde a um PDF ou DOCX válido."}), 400

    try:
        profile = parse_resume(dest)
    except Exception:
        logger.exception("Falha ao ler currículo")
        _delete_resume_file(dest)
        return jsonify({"error": "Não foi possível ler o currículo enviado."}), 400

    sess = store.get(sid)
    if sess.resume_path and sess.resume_path != dest:
        _delete_resume_file(sess.resume_path)
    sess.profile = profile
    sess.resume_path = dest
    sess.jobs.clear()
    sess.source_by_job.clear()
    _db().save_web_profile(sid, profile)
    _db().save_resume_version(sid, profile, file.filename)
    summary = _profile_summary(profile, dest)
    summary["job_hint"] = profile.job_titles[0] if profile.job_titles else (
        " ".join(profile.skills[:2]) if profile.skills else "desenvolvedor"
    )
    summary["suggested_keywords"] = _suggest_keywords(profile)
    return jsonify({"profile": summary})


@app.route("/api/search", methods=["POST"])
@require_profile
def api_search(sess: SessionData):
    if not sess.rate_ok("search", SEARCH_RATE_MAX, RATE_LIMIT_WINDOW):
        return jsonify({"error": "Muitas buscas seguidas. Aguarde alguns segundos."}), 429
    data = _json_object()
    sid = _sid()
    try:
        return jsonify(_run_search(sess, data, sid))
    except Exception:
        logger.exception("Erro na busca")
        return jsonify({"error": "Erro na busca. Tente novamente."}), 500


@app.route("/api/search/stream", methods=["POST"])
@require_profile
def api_search_stream(sess: SessionData):
    if not sess.rate_ok("search", SEARCH_RATE_MAX, RATE_LIMIT_WINDOW):
        return jsonify({"error": "Muitas buscas seguidas. Aguarde alguns segundos."}), 429
    data = _json_object()
    sid = _sid()

    def generate():
        q: queue.Queue = queue.Queue()
        holder: dict = {}

        def on_source(name: str, jobs: list) -> None:
            q.put({"event": "source", "source": name, "fetched": len(jobs), "count": len(jobs)})

        def on_partial(result) -> None:
            q.put({
                "event": "partial",
                "jobs": result.jobs,
                "sources": result.sources_status,
                "meta": result.meta,
            })

        def worker() -> None:
            try:
                holder["payload"] = _run_search(
                    sess, data, sid,
                    on_source_done=on_source,
                    on_partial=on_partial,
                )
            except Exception:
                logger.exception("Erro na busca em streaming")
                holder["error"] = "Erro na busca. Tente novamente."
            finally:
                q.put({"event": "_done"})

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = q.get()
            if item.get("event") == "_done":
                if holder.get("error"):
                    yield f"data: {json.dumps({'event': 'error', 'error': holder['error']}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'event': 'complete', **holder['payload']}, ensure_ascii=False)}\n\n"
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/job/detail", methods=["POST"])
@require_profile
def api_job_detail(sess: SessionData):
    data = _json_object()
    job_id = _job_id(data)
    job = sess.jobs.get(job_id) if job_id else None
    if not job:
        return jsonify({"error": "Vaga não encontrada — refaça a busca."}), 404
    _, _, sal = extract_salary(job)
    from cv_apply.matching import match_job
    match = match_job(sess.profile, job, use_semantic=False)
    return jsonify({
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "url": job.url,
        "description": job.description,
        "salary": sal,
        "source": sess.source_by_job.get(job.id, ""),
        "posted_at": _format_posted(job.posted_at),
        "easy_apply": job.easy_apply,
        "score": match.score,
        "breakdown": match.breakdown,
        "missing_skills": match.missing_skills,
        "fit_label": match.fit_label,
    })


@app.route("/api/meta", methods=["GET"])
def api_meta():
    from cv_apply import __version__

    full = os.getenv("VAGA_EM_VISTA_FULL", os.getenv("HIREPILOT_FULL", "")).lower() in {
        "1", "true", "yes"
    }
    return jsonify({
        "version": __version__,
        "variant": "full" if full else "lite",
        "release_url": "https://github.com/ericnacif/HirePilot/releases/latest",
        "csrf_token": _csrf_token(),
    })


_MUNICIPIOS_CACHE: dict[str, list[str]] | None = None


def _load_municipios() -> dict[str, list[str]]:
    global _MUNICIPIOS_CACHE
    if _MUNICIPIOS_CACHE is None:
        path = Path(__file__).resolve().parent / "data" / "br_municipios.json"
        _MUNICIPIOS_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return _MUNICIPIOS_CACHE


@app.route("/api/locations/cities", methods=["GET"])
def api_location_cities():
    from cv_apply.locations import strip_accents

    uf = (request.args.get("state") or "").upper()[:2]
    q = strip_accents((request.args.get("q") or "").strip())
    data = _load_municipios()
    if uf and uf in data:
        pool = data[uf]
    else:
        pool = [c for cities in data.values() for c in cities]
    if q:
        pool = [
            c for c in pool
            if strip_accents(c).startswith(q) or q in strip_accents(c)
        ]
    return jsonify(pool[:30])


@app.route("/api/state", methods=["GET"])
def api_state_get():
    sid = _sid()
    return jsonify(_db().get_web_state(sid))


@app.route("/api/state/favorite", methods=["POST"])
def api_state_favorite():
    data = _json_object()
    sid = _sid()
    job_id = _job_id(data)
    if not job_id:
        return jsonify({"error": "id ausente"}), 400
    db = _db()
    if data.get("favorite"):
        db.save_favorite(sid, job_id, data.get("meta") or {"id": job_id})
    else:
        db.remove_favorite(sid, job_id)
    return jsonify({"ok": True})


@app.route("/api/state/applied", methods=["POST"])
def api_state_applied():
    data = _json_object()
    sid = _sid()
    job_id = _job_id(data)
    if not job_id:
        return jsonify({"error": "id ausente"}), 400
    db = _db()
    if data.get("applied"):
        meta = data.get("meta") or {"id": job_id}
        db.save_applied_meta(sid, job_id, meta)
    else:
        db.remove_applied_meta(sid, job_id)
    return jsonify({"ok": True})


@app.route("/api/applications", methods=["GET"])
def api_applications():
    return jsonify({"applications": list(_db().get_web_state(_sid())["applied"].values())})


@app.route("/api/applications/status", methods=["POST"])
def api_application_status():
    data = _json_object()
    job_id = _job_id(data)
    status = data.get("status")
    allowed = {"saved", "applied", "interview", "offer", "rejected", "withdrawn"}
    if not job_id or not isinstance(status, str) or status not in allowed:
        return jsonify({"error": "Vaga ou status inválido."}), 400
    sid = _sid()
    state = _db().get_web_state(sid)
    meta = dict(state["applied"].get(job_id) or {"id": job_id})
    meta["status"] = status
    _db().save_applied_meta(sid, job_id, meta)
    return jsonify({"ok": True, "application": meta})


@app.route("/api/resume/versions", methods=["GET"])
def api_resume_versions():
    return jsonify({"versions": _db().list_resume_versions(_sid())})


@app.route("/api/privacy/export", methods=["GET"])
def api_privacy_export():
    payload = json.dumps(_db().export_web_data(_sid()), ensure_ascii=False, indent=2)
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=vaga-em-vista-dados.json"},
    )


@app.route("/api/privacy/delete", methods=["POST"])
def api_privacy_delete():
    sid = _sid()
    sess = store.delete(sid)
    if sess:
        _delete_resume_file(sess.resume_path)
    _db().delete_web_data(sid)
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/diagnostics", methods=["GET"])
def api_diagnostics():
    settings = get_settings()
    db_path = settings.data_dir / "cv_apply.db"
    return jsonify({
        "ok": True,
        "version": __import__("cv_apply").__version__,
        "variant": "full" if os.getenv("VAGA_EM_VISTA_FULL", "").lower() in {"1", "true", "yes"} else "lite",
        "sources": [{"name": name, "configured": name in settings.search_sources} for name in AVAILABLE_SOURCES],
        "semantic": {"configured": settings.use_semantic_matching},
        "data_dir": str(settings.data_dir),
        "database": {"exists": db_path.exists(), "size_bytes": db_path.stat().st_size if db_path.exists() else 0},
    })


@app.route("/api/job/import", methods=["POST"])
@require_profile
def api_job_import(sess: SessionData):
    data = _json_object()
    url = data.get("url", "")
    title = data.get("title", "")
    company = data.get("company", "Empresa não informada")
    location = data.get("location", "")
    description = data.get("description", "")
    from urllib.parse import urlparse
    if not isinstance(url, str) or urlparse(url).scheme not in {"http", "https"} or not urlparse(url).netloc:
        return jsonify({"error": "Informe uma URL http(s) válida."}), 400
    if not isinstance(title, str) or not 2 <= len(title.strip()) <= 200:
        return jsonify({"error": "Informe o título da vaga."}), 400
    if not isinstance(company, str) or not isinstance(description, str) or len(company) > 160 or len(description) > 20000:
        return jsonify({"error": "Dados da vaga muito grandes."}), 400
    raw_id = f"{url.strip()}|{title.strip()}|{company.strip()}"
    job = JobPosting(
        id="manual-" + hashlib.sha256(raw_id.encode()).hexdigest()[:32],
        title=title.strip(), company=company.strip() or "Empresa não informada",
        location=str(location)[:200], url=url.strip(), description=str(description).strip(),
        posted_at=datetime.now().isoformat(),
    )
    sess.jobs[job.id] = job
    sess.source_by_job[job.id] = "manual"
    _db().save_jobs([job])
    from cv_apply.matching import match_job
    match = match_job(sess.profile, job, use_semantic=False)
    return jsonify({"job": job_row(match, sess.profile, source="manual", applied=False, is_new=True, format_posted=_format_posted)})


@app.route("/api/alerts", methods=["GET", "POST", "DELETE"])
@require_profile
def api_alerts(sess: SessionData):
    sid = _sid()
    db = _db()
    if request.method == "GET":
        return jsonify({"alerts": db.get_web_state(sid)["alerts"]})
    data = _json_object()
    if request.method == "DELETE":
        alert_id = _positive_int(data.get("id"))
        if data.get("id") is not None and alert_id is None:
            return jsonify({"error": "id inválido"}), 400
        if alert_id:
            db.delete_alert(sid, alert_id)
        return jsonify({"ok": True})
    name_value = data.get("name")
    name = name_value.strip() if isinstance(name_value, str) else ""
    filters = data.get("filters")
    if not isinstance(name, str) or not 1 <= len(name) <= 120:
        return jsonify({"error": "Nome e filtros são obrigatórios."}), 400
    if not isinstance(filters, dict) or not filters:
        return jsonify({"error": "Nome e filtros são obrigatórios."}), 400
    # Só persiste o perfil quando a pessoa ativa um recurso que precisa dele
    # depois da requisição; uploads comuns continuam apenas na memória/sessão.
    db.save_web_profile(sid, sess.profile)
    raw_alert_id = data.get("id")
    alert_id = _positive_int(raw_alert_id)
    if raw_alert_id is not None and alert_id is None:
        return jsonify({"error": "id inválido"}), 400
    aid = db.save_alert(sid, name, filters, alert_id)
    return jsonify({"ok": True, "id": aid})


@app.route("/api/alerts/toggle", methods=["POST"])
@require_profile
def api_alerts_toggle(sess: SessionData):
    sid = _sid()
    data = _json_object()
    alert_id = _positive_int(data.get("id"))
    if not alert_id:
        return jsonify({"error": "id ausente"}), 400
    _db().set_alert_enabled(sid, alert_id, bool(data.get("enabled", True)))
    return jsonify({"ok": True})


@app.route("/api/alerts/hits", methods=["POST"])
def api_alert_hits():
    global _alert_hits
    sid = _sid()
    hits = [hit for hit in _alert_hits if hit.get("sid") == sid]
    _alert_hits = [hit for hit in _alert_hits if hit.get("sid") != sid]
    return jsonify({"hits": hits})


@app.route("/api/ats", methods=["POST"])
@require_job
def api_ats(sess: SessionData, job: JobPosting, data: dict):
    report = analyze_ats(sess.profile, job, resume_path=sess.resume_path)
    return jsonify({
        "coverage": report.keyword_coverage,
        "ats_score": report.ats_score,
        "present": report.present_keywords,
        "missing": report.missing_keywords,
        "suggestions": report.suggestions,
    })


@app.route("/api/tailor", methods=["POST"])
@require_job
def api_tailor(sess: SessionData, job: JobPosting, data: dict):
    md = tailor_resume_markdown(sess.profile, job, sess.resume_path)
    return jsonify({"markdown": md})


@app.route("/api/cover", methods=["POST"])
@require_job
def api_cover(sess: SessionData, job: JobPosting, data: dict):
    lang_value = data.get("lang")
    lang = lang_value.lower() if isinstance(lang_value, str) else None
    letter = generate_cover_letter(sess.profile, job, get_settings(), lang=lang)
    return jsonify({"letter": letter})


_EXPORT_COLUMNS = [
    "score", "ats", "title", "company", "location", "source",
    "posted_at", "easy_apply", "applied", "url",
]


@app.route("/api/export")
def api_export():
    """Exporta vagas (opcionalmente filtradas por fonte / favoritas / aplicadas)."""
    sess = store.get(_sid())
    rows = list(sess.last_results if sess else [])
    fmt = (request.args.get("format") or "csv").lower()
    source = (request.args.get("source") or "").strip()
    favorites_only = request.args.get("favorites") == "1"
    hide_applied = request.args.get("hide_applied") == "1"

    if source or favorites_only or hide_applied:
        sid = _sid()
        state = _db().get_web_state(sid)
        fav_ids = set(state.get("favorites", {}).keys())
        applied_ids = set(state.get("applied", {}).keys())
        if sess:
            applied_ids |= sess.applied
        filtered = []
        for row in rows:
            if source and row.get("source") != source:
                continue
            if favorites_only and row.get("id") not in fav_ids:
                continue
            if hide_applied and (row.get("applied") or row.get("id") in applied_ids):
                continue
            filtered.append(row)
        rows = filtered

    if fmt == "json":
        payload = json.dumps(rows, ensure_ascii=False, indent=2)
        return Response(
            payload,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=vagas.json"},
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=vagas.csv"},
    )


@app.route("/api/profile", methods=["POST"])
@require_profile
def api_profile(sess: SessionData):
    data = _json_object()
    seniority_value = data.get("seniority")
    seniority = seniority_value.strip().lower() if isinstance(seniority_value, str) else ""
    sess.profile.seniority = seniority if seniority in VALID_SENIORITY else None
    return jsonify({"ok": True, "seniority": sess.profile.seniority})


@app.route("/api/applied", methods=["POST"])
@require_profile
def api_applied(sess: SessionData):
    data = _json_object()
    job_id = _job_id(data)
    if not job_id:
        return jsonify({"error": "id ausente"})
    if data.get("applied"):
        sess.applied.add(job_id)
        _db().save_applied_meta(_sid(), job_id, data.get("meta") or {"id": job_id})
    else:
        sess.applied.discard(job_id)
        _db().remove_applied_meta(_sid(), job_id)
    return jsonify({"ok": True, "applied": job_id in sess.applied})


def _port_in_use(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def run_server(
    host: str = "127.0.0.1",
    port: int = 5000,
    open_browser: bool = True,
) -> None:
    if _port_in_use(host, port):
        raise OSError(f"A porta {port} já está em uso; escolha outra porta.")

    settings = get_settings()
    _cleanup_stale_uploads(settings.data_dir / "uploads")
    _warmup_semantic()

    def _notify_hits(hits: list[dict]) -> None:
        global _alert_hits
        _alert_hits.extend(hits)
        for h in hits:
            logger.info("Alerta '%s': %d vaga(s) nova(s)", h.get("name"), h.get("new_count"))

    from cv_apply.alert_scheduler import start_alert_scheduler

    start_alert_scheduler(settings.data_dir, on_hits=_notify_hits)

    url = f"http://{host}:{port}"
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, use_reloader=False)
