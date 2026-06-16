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
import threading
import time
import uuid
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, session
from werkzeug.utils import secure_filename

from cv_apply.ats import analyze_ats, analyze_resume_format
from cv_apply.config import get_settings
from cv_apply.cover_letter import generate_cover_letter
from cv_apply.matching import rank_jobs
from cv_apply.profile import CandidateProfile, JobPosting
from cv_apply.resume_parser import parse_resume
from cv_apply.sources import AVAILABLE_SOURCES, dedupe_jobs, run_sources
from cv_apply.tailor import tailor_resume_markdown

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("CV_APPLY_SECRET", os.urandom(24).hex())

ALLOWED_EXT = {".pdf", ".docx", ".doc"}
VALID_SENIORITY = {"estagiário", "júnior", "pleno", "sênior"}
SESSION_TTL_SECONDS = 2 * 60 * 60  # 2h sem uso → expira
UPLOAD_RETENTION_SECONDS = int(os.getenv("UPLOAD_RETENTION_HOURS", "24")) * 60 * 60
MAX_SESSIONS = 200


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
    last_seen: float = field(default_factory=time.time)


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
# Rotas                                                                        #
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    _sid()
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def api_upload():
    sid = _sid()
    file = request.files.get("resume")
    if not file or not file.filename:
        return jsonify({"error": "Nenhum arquivo enviado."})

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "Formato inválido. Envie PDF ou DOCX."})

    settings = get_settings()
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_uploads(upload_dir)
    dest = upload_dir / f"{sid}_{secure_filename(file.filename)}"
    file.save(str(dest))

    try:
        profile = parse_resume(dest)
    except Exception as exc:
        logger.exception("Falha ao ler currículo")
        _delete_resume_file(dest)
        return jsonify({"error": f"Não foi possível ler o currículo: {exc}"})

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
    return jsonify({"profile": summary})


@app.route("/api/search", methods=["POST"])
@require_profile
def api_search(sess: SessionData):
    data = request.get_json(silent=True) or {}
    settings = get_settings()
    settings.search_keywords = data.get("keywords") or "desenvolvedor"
    settings.search_location = data.get("location") or "Brasil"
    settings.search_workplace = [w.lower() for w in data.get("workplace", [])]
    settings.search_job_type = [j.lower() for j in data.get("job_type", [])]
    settings.search_experience = [e.lower() for e in data.get("experience", [])]
    settings.search_date_posted = (data.get("date_posted") or "qualquer").lower()
    sources = [s.lower() for s in data.get("sources", []) if s.lower() in AVAILABLE_SOURCES]
    settings.search_sources = sources or ["gupy"]
    limit = max(1, min(int(data.get("limit") or 20), 100))

    results = run_sources(settings, max_jobs=limit, on_log=lambda m: logger.info(m))

    source_by_id: dict[str, str] = {}
    all_jobs: list[JobPosting] = []
    for src_name, jobs in results.items():
        for job in jobs:
            source_by_id[job.id] = src_name
            all_jobs.append(job)
    if not all_jobs:
        return jsonify({"jobs": []})

    all_jobs = dedupe_jobs(all_jobs)
    matches = rank_jobs(
        sess.profile, all_jobs, min_score=0, use_semantic=settings.use_semantic_matching
    )

    sess.jobs = {}
    sess.source_by_job = source_by_id

    out = []
    for m in matches:
        sess.jobs[m.job.id] = m.job
        report = analyze_ats(sess.profile, m.job, resume_path=None)  # só cobertura (rápido)
        desc = (m.job.description or "").strip().replace("\n", " ")
        if len(desc) > 220:
            desc = desc[:220].rsplit(" ", 1)[0] + "…"
        out.append({
            "id": m.job.id, "title": m.job.title, "company": m.job.company,
            "location": m.job.location, "url": m.job.url, "score": m.score,
            "ats": report.keyword_coverage, "skills": m.skill_overlap[:8],
            "reasons": "; ".join(m.reasons[:2]),
            "source": source_by_id.get(m.job.id, ""),
            "posted_at": _format_posted(m.job.posted_at), "easy_apply": m.job.easy_apply,
            "description": desc,
            "applied": m.job.id in sess.applied,
        })
    sess.last_results = out
    return jsonify({"jobs": out})


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
    """Exporta as últimas vagas buscadas em CSV ou JSON."""
    sess = store.get(_sid())
    rows = sess.last_results if sess else []
    fmt = (request.args.get("format") or "csv").lower()

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
    else:
        sess.applied.discard(job_id)
    return jsonify({"ok": True, "applied": job_id in sess.applied})


def run_server(host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True) -> None:
    settings = get_settings()
    _cleanup_stale_uploads(settings.data_dir / "uploads")
    url = f"http://{host}:{port}"
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, use_reloader=False)
