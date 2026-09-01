"""Micro-interface web reutilizável: cada pessoa sobe o currículo, recebe a
nota ATS e busca/ranqueia/aplica em vagas. Estado isolado por sessão.

O front-end fica em ``templates/index.html`` + ``static/`` (CSS e JS).
O estado por sessão é guardado em memória com expiração automática
(:class:`SessionStore`) para não crescer indefinidamente.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import queue
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
from cv_apply.search_pipeline import apply_payload_to_settings, execute_search
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
    PERMANENT_SESSION_LIFETIME=SESSION_TTL_SECONDS if "SESSION_TTL_SECONDS" in globals() else 7200,
    TRUSTED_HOSTS=WEB_ALLOWED_HOSTS or None,
)
if os.getenv("TRUST_PROXY", "false").lower() in {"1", "true", "yes"}:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

ALLOWED_EXT = {".pdf", ".docx"}
VALID_SENIORITY = {"estagiário", "júnior", "pleno", "sênior"}
SESSION_TTL_SECONDS = 2 * 60 * 60  # 2h sem uso → expira
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
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


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
        sess = store.get(_sid())
        if not sess or not sess.profile:
            return jsonify({"error": "Envie seu currículo primeiro."})
        return fn(sess, *args, **kwargs)

    return wrapper


def require_job(fn: Callable) -> Callable:
    """Como :func:`require_profile`, mas também resolve a vaga pelo ``id``."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        sess = store.get(_sid())
        if not sess or not sess.profile:
            return jsonify({"error": "Envie seu currículo primeiro."})
        data = request.get_json(silent=True) or {}
        job = sess.jobs.get(data.get("id"))
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
    except Exception as exc:
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
    data = request.get_json(silent=True) or {}
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
    data = request.get_json(silent=True) or {}
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
            except Exception as exc:
                holder["error"] = str(exc)
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
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/job/detail", methods=["POST"])
@require_profile
def api_job_detail(sess: SessionData):
    data = request.get_json(silent=True) or {}
    job = sess.jobs.get(data.get("id"))
    if not job:
        return jsonify({"error": "Vaga não encontrada — refaça a busca."}), 404
    _, _, sal = extract_salary(job)
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
    })


@app.route("/api/meta", methods=["GET"])
def api_meta():
    from cv_apply import __version__

    full = os.getenv("HIREPILOT_FULL", "").lower() in {"1", "true", "yes"}
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
    data = request.get_json(silent=True) or {}
    sid = _sid()
    job_id = data.get("id")
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
    data = request.get_json(silent=True) or {}
    sid = _sid()
    job_id = data.get("id")
    if not job_id:
        return jsonify({"error": "id ausente"}), 400
    db = _db()
    if data.get("applied"):
        meta = data.get("meta") or {"id": job_id}
        db.save_applied_meta(sid, job_id, meta)
    else:
        db.remove_applied_meta(sid, job_id)
    return jsonify({"ok": True})


@app.route("/api/alerts", methods=["GET", "POST", "DELETE"])
@require_profile
def api_alerts(sess: SessionData):
    sid = _sid()
    db = _db()
    if request.method == "GET":
        return jsonify({"alerts": db.get_web_state(sid)["alerts"]})
    data = request.get_json(silent=True) or {}
    if request.method == "DELETE":
        alert_id = int(data.get("id", 0))
        if alert_id:
            db.delete_alert(sid, alert_id)
        return jsonify({"ok": True})
    name = (data.get("name") or "").strip()
    filters = data.get("filters")
    if not name or not filters:
        return jsonify({"error": "Nome e filtros são obrigatórios."}), 400
    # Só persiste o perfil quando a pessoa ativa um recurso que precisa dele
    # depois da requisição; uploads comuns continuam apenas na memória/sessão.
    db.save_web_profile(sid, sess.profile)
    aid = db.save_alert(sid, name, filters, data.get("id"))
    return jsonify({"ok": True, "id": aid})


@app.route("/api/alerts/toggle", methods=["POST"])
@require_profile
def api_alerts_toggle(sess: SessionData):
    sid = _sid()
    data = request.get_json(silent=True) or {}
    alert_id = int(data.get("id", 0))
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
    lang = (data.get("lang") or "").lower() or None
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
    data = request.get_json(silent=True) or {}
    seniority = (data.get("seniority") or "").strip().lower()
    sess.profile.seniority = seniority if seniority in VALID_SENIORITY else None
    return jsonify({"ok": True, "seniority": sess.profile.seniority})


@app.route("/api/applied", methods=["POST"])
@require_profile
def api_applied(sess: SessionData):
    data = request.get_json(silent=True) or {}
    job_id = data.get("id")
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


def _free_port(host: str, port: int) -> bool:
    """Tenta encerrar o processo que está ocupando ``port`` (Windows/Unix).

    Evita o problema de "código antigo em cache" quando há um servidor anterior
    rodando na mesma porta. Retorna True se a porta ficou livre.
    """
    import subprocess
    import sys

    pids: set[str] = set()
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in line and parts[1].endswith(f":{port}"):
                    pids.add(parts[-1])
            for pid in pids:
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, timeout=5)
        else:
            out = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True, timeout=5
            ).stdout
            pids = {p for p in out.split() if p}
            for pid in pids:
                subprocess.run(["kill", "-9", pid], capture_output=True, timeout=5)
    except Exception as exc:
        logger.warning("Não consegui liberar a porta %d automaticamente: %s", port, exc)
        return False

    if pids:
        time.sleep(1.0)
        logger.info("Porta %d liberada (encerrei: %s)", port, ", ".join(pids))
    return not _port_in_use(host, port)


def run_server(
    host: str = "127.0.0.1",
    port: int = 5000,
    open_browser: bool = True,
    free_port: bool = True,
) -> None:
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

    if free_port and _port_in_use(host, port):
        logger.info("Porta %d ocupada — tentando liberar (servidor antigo?)...", port)
        _free_port(host, port)
    url = f"http://{host}:{port}"
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, use_reloader=False)
